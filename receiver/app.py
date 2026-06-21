from __future__ import annotations

import json
import math
import os
import threading
import time
import zlib
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

from protocol import bits_to_bytes, crc16_ccitt

cv2.setUseOptimized(True)

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class ReceiverState:
    mode: str = "screen"
    camera_index: int = 0
    running: bool = True
    tracking_mode: str = "center"
    grid_cols: int = 25
    grid_rows: int = 50
    screen_frames_seen: int = 0
    screen_decode_attempts: int = 0
    screen_crc_failures: int = 0
    screen_magic_failures: int = 0
    optical_frames_ok: int = 0
    pulse_bits_seen: int = 0
    last_message: str = ""
    last_message_at: int = 0
    last_payload_type: str = "text"
    last_image_bytes: bytes = b""
    last_image_name: str = ""
    last_image_size: int = 0
    last_file_bytes: bytes = b""
    last_file_name: str = ""
    last_file_size: int = 0
    last_error: str = ""
    fps: float = 0.0
    brightness: float = 0.0
    threshold: float = 0.0
    decoder_status: str = "idle"
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=80))
    frame_events: deque[str] = field(default_factory=lambda: deque(maxlen=80))

    def log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.logs.appendleft(f"{stamp} {text}")

    def frame_log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.frame_events.appendleft(f"{stamp} {text}")


class ScreenGridDecoder:
    MIN_GRID_COLS = 12
    MAX_GRID_COLS = 60
    MIN_GRID_ROWS = 12
    MAX_GRID_ROWS = 80
    CALIBRATION_CELLS = 8

    def __init__(self, state: ReceiverState):
        self.state = state
        self.current_tx_id: int | None = None
        self.frames: dict[int, bytes] = {}
        self.total = 0
        self.flags = 0
        self.original_len = 0
        self.sample_points: np.ndarray | None = None
        self.last_panel_box: tuple[int, int, int, int] | None = None

    @property
    def grid_cols(self) -> int:
        return max(self.MIN_GRID_COLS, min(self.MAX_GRID_COLS, int(self.state.grid_cols)))

    @property
    def grid_rows(self) -> int:
        return max(self.MIN_GRID_ROWS, min(self.MAX_GRID_ROWS, int(self.state.grid_rows)))

    @property
    def frame_bytes(self) -> int:
        usable_symbols = max(0, self.grid_cols * self.grid_rows - self.CALIBRATION_CELLS)
        return max(32, (usable_symbols * 3) // 8)

    @property
    def chunk_size(self) -> int:
        return max(1, self.frame_bytes - 16)

    def reset(self) -> None:
        self.current_tx_id = None
        self.frames.clear()
        self.total = 0
        self.flags = 0
        self.original_len = 0
        self.last_panel_box = None

    def process(self, frame: np.ndarray) -> tuple[str | None, np.ndarray | None]:
        warped = self._extract_code_panel(frame)
        if warped is None:
            self.state.decoder_status = f"screen: buscando panel {self.grid_cols}x{self.grid_rows}"
            return None, None

        self.state.screen_frames_seen += 1
        self.state.screen_decode_attempts += 1

        parsed = None
        failure_headers: list[str] = []
        saw_crc_failure = False
        for variant, payload in self._sample_payload_candidates(warped):
            candidate, failure = self._parse_grid_frame(payload)
            if candidate is not None:
                parsed = candidate
                if variant != "normal":
                    self.state.frame_log(f"orientacion corregida: {variant}")
                break
            if failure.startswith("magic:"):
                failure_headers.append(f"{variant}={failure[6:]}")
            elif failure == "crc":
                saw_crc_failure = True

        if parsed is not None:
            tx_id, flags, seq, total, original_len, chunk = parsed
            if self.current_tx_id != tx_id:
                self.current_tx_id = tx_id
                self.frames.clear()
                self.total = total
                self.flags = flags
                self.original_len = original_len
                compression = "zlib" if flags & 1 else "raw"
                self.state.log(f"screen-color: nueva transmision tx={tx_id}, tramas={total}, {compression}")

            if seq not in self.frames:
                self.frames[seq] = chunk
                self.state.optical_frames_ok += 1
                self.state.log(f"screen-color: trama {seq + 1}/{total} recibida")
                self.state.frame_log(f"OK tx={tx_id} trama {seq + 1}/{total} bytes={len(chunk)}")

            self.state.decoder_status = f"screen: {len(self.frames)}/{self.total} tramas"
            if self.total and len(self.frames) >= self.total:
                data = b"".join(self.frames[index] for index in range(self.total))
                try:
                    if self.flags & 1:
                        data = zlib.decompress(data)
                    message = self._consume_payload(data)
                except zlib.error as exc:
                    self.state.log(f"screen-color: zlib invalido {exc}")
                    self.reset()
                    return None, warped
                self.state.log(f"screen-color: mensaje completo ({len(message)} chars)")
                self.reset()
                return message, warped

        if saw_crc_failure:
            self.state.screen_crc_failures += 1
            if self.state.screen_crc_failures <= 8 or self.state.screen_crc_failures % 20 == 0:
                self.state.frame_log("CRC fallo en candidatos de orientacion")
        else:
            self.state.screen_magic_failures += 1
            if self.state.screen_magic_failures <= 5 or self.state.screen_magic_failures % 30 == 0:
                sample = " ".join(failure_headers[:4]) if failure_headers else "sin header"
                self.state.frame_log(f"magic fallo {sample}")
        self.state.decoder_status = "screen: panel detectado, sin trama valida"
        return None, warped

    def _consume_payload(self, data: bytes) -> str:
        if data.startswith(b"TXT1"):
            message = data[4:].decode("utf-8", errors="replace")
            self.state.last_payload_type = "text"
            self.state.last_image_bytes = b""
            self.state.last_image_name = ""
            self.state.last_image_size = 0
            self.state.last_file_bytes = b""
            self.state.last_file_name = ""
            self.state.last_file_size = 0
            return message

        if data.startswith(b"IMG1") and len(data) >= 10:
            original_size = int.from_bytes(data[4:8], "big")
            name_len = int.from_bytes(data[8:10], "big")
            name_start = 10
            name_end = name_start + name_len
            if name_end <= len(data):
                name = data[name_start:name_end].decode("utf-8", errors="replace")
                image_bytes = data[name_end:]
                self.state.last_payload_type = "image"
                self.state.last_image_bytes = image_bytes
                self.state.last_image_name = name or "received.jpg"
                self.state.last_image_size = len(image_bytes)
                self.state.last_file_bytes = b""
                self.state.last_file_name = ""
                self.state.last_file_size = 0
                return f"Imagen recibida: {self.state.last_image_name}\n{original_size} B -> {len(image_bytes)} B"

        if data.startswith(b"FIL1") and len(data) >= 10:
            original_size = int.from_bytes(data[4:8], "big")
            name_len = int.from_bytes(data[8:10], "big")
            name_start = 10
            name_end = name_start + name_len
            if name_end <= len(data):
                name = data[name_start:name_end].decode("utf-8", errors="replace")
                file_bytes = data[name_end:]
                self.state.last_payload_type = "file"
                self.state.last_file_bytes = file_bytes
                self.state.last_file_name = name or "received.bin"
                self.state.last_file_size = len(file_bytes)
                self.state.last_image_bytes = b""
                self.state.last_image_name = ""
                self.state.last_image_size = 0
                return f"Archivo recibido: {self.state.last_file_name}\n{original_size} B -> {len(file_bytes)} B"

        self.state.last_payload_type = "text"
        self.state.last_image_bytes = b""
        self.state.last_image_name = ""
        self.state.last_image_size = 0
        self.state.last_file_bytes = b""
        self.state.last_file_name = ""
        self.state.last_file_size = 0
        return data.decode("utf-8", errors="replace")

    def _parse_grid_frame(self, payload: bytes) -> tuple[tuple[int, int, int, int, int, bytes] | None, str]:
        frame_bytes = self.frame_bytes
        chunk_size = self.chunk_size
        if len(payload) < frame_bytes:
            return None, "short"
        if payload[0:2] != b"OC" or payload[2] != 3:
            return None, f"magic:{payload[:4].hex()}"
        flags = payload[3]
        tx_id = payload[4]
        seq = (payload[5] << 8) | payload[6]
        total = (payload[7] << 8) | payload[8]
        chunk_len = (payload[9] << 8) | payload[10]
        original_len = (payload[11] << 8) | payload[12]
        if total == 0 or seq >= total or chunk_len > chunk_size:
            return None, "header"
        expected = int.from_bytes(payload[frame_bytes - 2 : frame_bytes], "big")
        actual = crc16_ccitt(payload[0 : frame_bytes - 2])
        if expected != actual:
            return None, "crc"
        return (tx_id, flags, seq, total, original_len, payload[14 : 14 + chunk_len]), "ok"

    def _extract_code_panel(self, frame: np.ndarray) -> np.ndarray | None:
        self.last_panel_box = None
        return self._extract_center_panel(frame)

    def _extract_center_panel(self, frame: np.ndarray) -> np.ndarray | None:
        height, width = frame.shape[:2]
        target_ratio = self.grid_cols / self.grid_rows
        panel_h = int(height * 0.62)
        panel_w = int(panel_h * target_ratio)
        if panel_w > int(width * 0.40):
            panel_w = int(width * 0.40)
            panel_h = int(panel_w / target_ratio)
        x0 = max(0, (width - panel_w) // 2)
        y0 = max(0, (height - panel_h) // 2)
        crop = frame[y0 : y0 + panel_h, x0 : x0 + panel_w]
        self.last_panel_box = (x0, y0, panel_w, panel_h)
        if crop.size == 0:
            return None
        return cv2.resize(crop, (self.grid_cols * 12, self.grid_rows * 12), interpolation=cv2.INTER_AREA)

    def _find_texture_grid_panel(self, frame: np.ndarray) -> tuple[int, int, int, int] | None:
        height, width = frame.shape[:2]
        roi_w = int(width * 0.58)
        roi_h = int(height * 0.92)
        roi_x = (width - roi_w) // 2
        roi_y = (height - roi_h) // 2
        roi = frame[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
        if roi.size == 0:
            return None

        scale = 360 / max(1, roi.shape[1])
        small_w = 360
        small_h = max(1, int(roi.shape[0] * scale))
        small = cv2.resize(roi, (small_w, small_h), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        grad_x = cv2.Sobel(gray, cv2.CV_16S, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_16S, 0, 1, ksize=3)
        mag = cv2.addWeighted(cv2.convertScaleAbs(grad_x), 0.5, cv2.convertScaleAbs(grad_y), 0.5, 0)
        _, edge_mask = cv2.threshold(mag, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        sat_mask = cv2.inRange(hsv[:, :, 1], 28, 255)
        val_mask = cv2.inRange(hsv[:, :, 2], 35, 255)
        chroma_mask = cv2.bitwise_and(sat_mask, val_mask)
        mask = cv2.bitwise_or(edge_mask, chroma_mask)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        target_ratio = self.grid_cols / self.grid_rows
        best: tuple[float, tuple[int, int, int, int]] | None = None
        small_area = small_w * small_h
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < small_area * 0.025:
                continue
            ratio = w / max(1, h)
            if not 0.28 <= ratio <= 0.95:
                continue
            region = mask[y : y + h, x : x + w]
            density = cv2.countNonZero(region) / max(1, area)
            if density < 0.08:
                continue
            ratio_score = 1.0 - min(abs(ratio - target_ratio) / max(target_ratio, 0.01), 1.0)
            center_score = 1.0 - min(abs((x + w / 2) - small_w / 2) / (small_w / 2), 1.0)
            score = area * (0.45 + density) * (0.35 + ratio_score) * (0.45 + center_score)
            if best is None or score > best[0]:
                best = (score, (x, y, w, h))

        if best is None:
            return None

        x, y, w, h = best[1]
        cx = x + w / 2
        cy = y + h / 2
        current_ratio = w / max(1, h)
        if current_ratio > target_ratio:
            new_h = h
            new_w = int(round(new_h * target_ratio))
        else:
            new_w = w
            new_h = int(round(new_w / target_ratio))
        new_w = int(round(new_w * 1.06))
        new_h = int(round(new_h * 1.06))
        x0 = max(0, int(round(cx - new_w / 2)))
        y0 = max(0, int(round(cy - new_h / 2)))
        x1 = min(small_w, x0 + new_w)
        y1 = min(small_h, y0 + new_h)
        inv = 1.0 / scale
        fx0 = max(0, roi_x + int(round(x0 * inv)))
        fy0 = max(0, roi_y + int(round(y0 * inv)))
        fx1 = min(width, roi_x + int(round(x1 * inv)))
        fy1 = min(height, roi_y + int(round(y1 * inv)))
        if fx1 - fx0 < 20 or fy1 - fy0 < 40:
            return None
        return fx0, fy0, fx1 - fx0, fy1 - fy0

    def _find_color_grid_quad(self, frame: np.ndarray) -> np.ndarray | None:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        mask = cv2.inRange(sat, 45, 255)
        mask = cv2.bitwise_and(mask, cv2.inRange(val, 35, 255))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        connected = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
        contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = frame.shape[0] * frame.shape[1]
        quad = self._quad_from_contours(contours, frame_area)
        if quad is not None:
            return self._expand_quad(quad, 1.04, 1.04)

        points = cv2.findNonZero(mask)
        if points is None or len(points) < 400:
            return None
        rect = cv2.minAreaRect(points)
        (cx, cy), (rw, rh), _ = rect
        if rw <= 1 or rh <= 1:
            return None
        long_side = max(rw, rh)
        short_side = min(rw, rh)
        ratio = short_side / max(1.0, long_side)
        area = rw * rh
        if area < frame_area * 0.015 or not 0.35 <= ratio <= 0.68:
            return None
        box = cv2.boxPoints(rect).astype(np.float32)
        ordered = self._order_points(box)
        width_est = np.linalg.norm(ordered[1] - ordered[0])
        height_est = np.linalg.norm(ordered[3] - ordered[0])
        if width_est > height_est:
            # Rotate point order so the target stays vertical.
            ordered = np.array([ordered[1], ordered[2], ordered[3], ordered[0]], dtype=np.float32)
        return self._expand_quad(ordered, 1.16, 1.08)

    def _quad_from_contours(self, contours: list[np.ndarray], frame_area: int) -> np.ndarray | None:
        best: tuple[float, np.ndarray] | None = None
        target_ratio = self.grid_cols / self.grid_rows
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < frame_area * 0.012:
                continue
            perimeter = cv2.arcLength(contour, True)
            if perimeter <= 0:
                continue
            approx = cv2.approxPolyDP(contour, 0.035 * perimeter, True)
            if len(approx) == 4:
                points = approx.reshape(4, 2).astype(np.float32)
            else:
                hull = cv2.convexHull(contour)
                rect = cv2.minAreaRect(hull)
                points = cv2.boxPoints(rect).astype(np.float32)
            ordered = self._order_points(points)
            width_est = (np.linalg.norm(ordered[1] - ordered[0]) + np.linalg.norm(ordered[2] - ordered[3])) * 0.5
            height_est = (np.linalg.norm(ordered[3] - ordered[0]) + np.linalg.norm(ordered[2] - ordered[1])) * 0.5
            if width_est <= 1 or height_est <= 1:
                continue
            ratio = width_est / height_est
            if not 0.25 <= ratio <= 0.85:
                continue
            ratio_score = 1.0 - min(abs(ratio - target_ratio) / max(target_ratio, 0.01), 1.0)
            score = area * (0.35 + ratio_score)
            if best is None or score > best[0]:
                best = (score, ordered)
        return best[1] if best else None

    def _find_color_grid_panel(self, frame: np.ndarray) -> tuple[int, int, int, int] | None:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        mask = cv2.inRange(sat, 45, 255)
        mask = cv2.bitwise_and(mask, cv2.inRange(val, 35, 255))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        projected = self._bbox_from_projection(mask, frame.shape[1], frame.shape[0])
        if projected is not None:
            return projected

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        frame_area = frame.shape[0] * frame.shape[1]
        best: tuple[float, tuple[int, int, int, int]] | None = None
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < frame_area * 0.015:
                continue
            ratio = w / max(1, h)
            if not 0.34 <= ratio <= 0.68:
                continue
            score = area * (1.0 - min(abs(ratio - 0.5), 0.5))
            if best is None or score > best[0]:
                x0, y0, x1, y1 = self._fit_ratio_box(x, y, w, h, frame.shape[1], frame.shape[0])
                best = (score, (x0, y0, x1 - x0, y1 - y0))
        return best[1] if best else None

    def _bbox_from_projection(self, mask: np.ndarray, max_w: int, max_h: int) -> tuple[int, int, int, int] | None:
        ys, xs = np.where(mask > 0)
        if len(xs) < 400:
            return None

        raw_x0, raw_x1 = int(xs.min()), int(xs.max()) + 1
        raw_y0, raw_y1 = int(ys.min()), int(ys.max()) + 1
        raw_w = raw_x1 - raw_x0
        raw_h = raw_y1 - raw_y0
        raw_ratio = raw_w / max(1, raw_h)
        raw_area = raw_w * raw_h
        if raw_area >= mask.shape[0] * mask.shape[1] * 0.012 and 0.34 <= raw_ratio <= 0.68:
            fx0, fy0, fx1, fy1 = self._fit_ratio_box(raw_x0, raw_y0, raw_w, raw_h, max_w, max_h)
            return fx0, fy0, fx1 - fx0, fy1 - fy0

        col_sum = np.count_nonzero(mask, axis=0)
        row_sum = np.count_nonzero(mask, axis=1)
        col_threshold = max(3, int(np.percentile(col_sum[col_sum > 0], 35))) if np.any(col_sum > 0) else 3
        row_threshold = max(3, int(np.percentile(row_sum[row_sum > 0], 35))) if np.any(row_sum > 0) else 3
        cols = np.where(col_sum >= col_threshold)[0]
        rows = np.where(row_sum >= row_threshold)[0]
        if len(cols) < 12 or len(rows) < 24:
            return None

        x0, x1 = int(cols.min()), int(cols.max()) + 1
        y0, y1 = int(rows.min()), int(rows.max()) + 1
        w = x1 - x0
        h = y1 - y0
        ratio = w / max(1, h)
        area = w * h
        if area < mask.shape[0] * mask.shape[1] * 0.015:
            return None
        if not 0.28 <= ratio <= 0.78:
            return None
        fx0, fy0, fx1, fy1 = self._fit_ratio_box(x0, y0, w, h, max_w, max_h)
        return fx0, fy0, fx1 - fx0, fy1 - fy0

    def _fit_ratio_box(self, x: int, y: int, w: int, h: int, max_w: int, max_h: int) -> tuple[int, int, int, int]:
        target_ratio = self.grid_cols / self.grid_rows
        cx = x + w / 2
        cy = y + h / 2
        current_ratio = w / max(1, h)
        if current_ratio > target_ratio:
            new_w = w
            new_h = int(round(new_w / target_ratio))
        else:
            new_h = h
            new_w = int(round(new_h * target_ratio))
        pad_x = 0
        pad_y = 0
        new_w += pad_x * 2
        new_h += pad_y * 2
        x0 = int(round(cx - new_w / 2))
        y0 = int(round(cy - new_h / 2))
        x0 = max(0, min(max_w - 1, x0))
        y0 = max(0, min(max_h - 1, y0))
        x1 = max(1, min(max_w, x0 + new_w))
        y1 = max(1, min(max_h, y0 + new_h))
        return x0, y0, x1, y1

    @staticmethod
    def _order_points(points: np.ndarray) -> np.ndarray:
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1).reshape(-1)
        ordered = np.zeros((4, 2), dtype=np.float32)
        ordered[0] = points[np.argmin(sums)]
        ordered[2] = points[np.argmax(sums)]
        ordered[1] = points[np.argmin(diffs)]
        ordered[3] = points[np.argmax(diffs)]
        return ordered

    @staticmethod
    def _expand_quad(points: np.ndarray, scale_x: float, scale_y: float) -> np.ndarray:
        center = points.mean(axis=0)
        top = (points[0] + points[1]) * 0.5
        bottom = (points[3] + points[2]) * 0.5
        left = (points[0] + points[3]) * 0.5
        right = (points[1] + points[2]) * 0.5
        x_axis = right - left
        y_axis = bottom - top
        half_x = x_axis * (scale_x * 0.5)
        half_y = y_axis * (scale_y * 0.5)
        return np.array(
            [
                center - half_x - half_y,
                center + half_x - half_y,
                center + half_x + half_y,
                center - half_x + half_y,
            ],
            dtype=np.float32,
        )

    def _sample_payload_candidates(self, warped: np.ndarray) -> list[tuple[str, bytes]]:
        candidates: list[tuple[str, bytes]] = []
        samples = self._sample_cell_fast(warped)
        candidates.append(("normal", self._payload_from_samples(samples)))
        candidates.append(("normal/fixed", self._payload_from_samples(samples, fixed_palette=True)))
        hflip = np.fliplr(samples)
        candidates.append(("hflip", self._payload_from_samples(hflip)))
        candidates.append(("hflip/fixed", self._payload_from_samples(hflip, fixed_palette=True)))
        return candidates

    def _symbol_offsets(self) -> tuple[int, ...]:
        return (0, 1, 2, 3, 4, 5, 6, 7, 8, self.grid_cols // 2, self.grid_cols, self.grid_cols + 1)

    def _sample_cell_fast(self, warped: np.ndarray) -> np.ndarray:
        return cv2.resize(warped, (self.grid_cols, self.grid_rows), interpolation=cv2.INTER_AREA).astype(np.float32)

    def _sample_cell_centers(self, warped: np.ndarray) -> np.ndarray:
        height, width = warped.shape[:2]
        cell_w = width / self.grid_cols
        cell_h = height / self.grid_rows
        radius_x = max(1, int(cell_w * 0.24))
        radius_y = max(1, int(cell_h * 0.24))
        out = np.zeros((self.grid_rows, self.grid_cols, 3), dtype=np.float32)
        for row in range(self.grid_rows):
            cy = int(round((row + 0.5) * cell_h))
            y0 = max(0, cy - radius_y)
            y1 = min(height, cy + radius_y + 1)
            for col in range(self.grid_cols):
                cx = int(round((col + 0.5) * cell_w))
                x0 = max(0, cx - radius_x)
                x1 = min(width, cx + radius_x + 1)
                patch = warped[y0:y1, x0:x1]
                if patch.size:
                    out[row, col] = np.median(patch.reshape(-1, 3), axis=0)
        return out

    def _payload_from_samples(self, grid_samples: np.ndarray, fixed_palette: bool = False, symbol_offset: int = 0) -> bytes:
        samples = grid_samples.reshape(-1, 3).astype(np.float32)
        if fixed_palette:
            calibration = np.array(
                [
                    [0, 0, 0],
                    [255, 0, 0],
                    [0, 255, 0],
                    [255, 255, 0],
                    [0, 0, 255],
                    [255, 0, 255],
                    [0, 255, 255],
                    [255, 255, 255],
                ],
                dtype=np.float32,
            )
        else:
            calibration = samples[: self.CALIBRATION_CELLS]
        data_start = min(len(samples), self.CALIBRATION_CELLS + max(0, symbol_offset))
        data_samples = samples[data_start:]
        distances = ((data_samples[:, None, :] - calibration[None, :, :]) ** 2).sum(axis=2)
        symbols = np.argmin(distances, axis=1).astype(np.uint8)
        self.state.threshold = float(np.sqrt(np.mean(np.min(distances, axis=1))))
        red_bits = ((symbols >> 2) & 1).astype(np.uint8)
        green_bits = ((symbols >> 1) & 1).astype(np.uint8)
        blue_bits = (symbols & 1).astype(np.uint8)
        triplets = np.column_stack((red_bits, green_bits, blue_bits)).reshape(-1)
        needed = self.frame_bytes * 8
        bits = triplets[:needed].tolist()
        return bits_to_bytes(bits[:needed])


class PulsePositionDecoder:
    def __init__(self, state: ReceiverState):
        self.state = state
        self.reset()

    def reset(self) -> None:
        self.phase = "wait_high"
        self.high_started: float | None = None
        self.low_started: float | None = None
        self.read_start: float | None = None
        self.samples: dict[int, list[tuple[float, float]]] = {}
        self.bits: list[int] = []
        self.min_brightness = 255.0
        self.max_brightness = 0.0
        self.last_level = False

    def process(self, frame: np.ndarray, ts: float, mode: str) -> str | None:
        height, width = frame.shape[:2]
        side = int(min(width, height) * 0.36)
        x0 = (width - side) // 2
        y0 = (height - side) // 2
        roi = frame[y0 : y0 + side, x0 : x0 + side]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        self.state.brightness = brightness

        self.min_brightness = min(self.min_brightness + 0.02, brightness)
        self.max_brightness = max(self.max_brightness - 0.02, brightness)
        observed_range = self.max_brightness - self.min_brightness
        if observed_range < 12.0:
            threshold = 180.0
        else:
            threshold = self.min_brightness + observed_range * 0.55
        self.state.threshold = threshold
        level = brightness >= threshold

        start_on = 0.85 if mode == "flash" else 0.45
        start_off = 0.88 if mode == "flash" else 0.40
        preamble_off = 0.90 if mode == "flash" else 0.42
        cell_seconds = 0.90 if mode == "flash" else 0.62

        if self.phase == "wait_high":
            self.state.decoder_status = f"{mode}: esperando pulso largo"
            if level:
                if self.high_started is None:
                    self.high_started = ts
                if ts - self.high_started >= start_on:
                    self.phase = "wait_low"
                    self.low_started = None
            else:
                self.high_started = None

        elif self.phase == "wait_low":
            self.state.decoder_status = f"{mode}: esperando silencio"
            if not level:
                if self.low_started is None:
                    self.low_started = ts
                if ts - self.low_started >= start_off:
                    self.phase = "reading"
                    self.read_start = self.low_started + preamble_off
                    self.samples.clear()
                    self.bits.clear()
                    self.state.log(f"{mode}: preambulo detectado")
            else:
                self.low_started = None

        elif self.phase == "reading":
            assert self.read_start is not None
            elapsed = ts - self.read_start
            index = int(elapsed / cell_seconds)
            offset = elapsed - index * cell_seconds
            self.samples.setdefault(index, []).append((offset / cell_seconds, brightness))

            while len(self.bits) < index:
                bit = self._decode_cell(self.samples.get(len(self.bits), []))
                if bit is None:
                    self.state.log(f"{mode}: celda ambigua, reinicio")
                    self.reset()
                    return None
                self.bits.append(bit)
                self.state.pulse_bits_seen = len(self.bits)
                parsed = self._try_parse(mode)
                if parsed is not None:
                    self.state.log(f"{mode}: mensaje completo ({len(parsed)} chars)")
                    self.reset()
                    return parsed

            if len(self.bits) > 600:
                self.state.log(f"{mode}: demasiados bits sin CRC, reinicio")
                self.reset()

            self.state.decoder_status = f"{mode}: leyendo {len(self.bits)} bits"

        self.last_level = level
        return None

    def _decode_cell(self, samples: list[tuple[float, float]]) -> int | None:
        if len(samples) < 2:
            return None
        first = [value for pos, value in samples if pos <= 0.45]
        last = [value for pos, value in samples if pos >= 0.55]
        if not first or not last:
            return None
        first_mean = sum(first) / len(first)
        last_mean = sum(last) / len(last)
        if abs(first_mean - last_mean) < 5:
            return None
        return 1 if first_mean > last_mean else 0

    def _try_parse(self, mode: str) -> str | None:
        data = bits_to_bytes(self.bits)
        magic = b"OL" if mode == "flash" else b"OI"
        if len(data) >= 2 and data[0:2] != magic:
            if len(self.bits) >= 24:
                self.state.log(f"{mode}: magic invalido, reinicio")
                self.reset()
            return None
        if len(data) < 4:
            return None
        if data[2] != 1:
            self.reset()
            return None
        payload_len = data[3]
        full_len = 2 + 1 + 1 + payload_len + 2
        if len(data) < full_len:
            return None
        frame = data[:full_len]
        expected = int.from_bytes(frame[-2:], "big")
        actual = crc16_ccitt(frame[:-2])
        if expected != actual:
            self.state.log(f"{mode}: CRC invalido")
            self.reset()
            return None
        return frame[4:-2].decode("utf-8", errors="replace")


class CameraWorker:
    def __init__(self, state: ReceiverState):
        self.state = state
        self.lock = threading.Lock()
        self.jpeg: bytes = b""
        self.stop_event = threading.Event()
        self.screen_decoder = ScreenGridDecoder(state)
        self.pulse_decoder = PulsePositionDecoder(state)
        self.capture: cv2.VideoCapture | None = None

    def start(self) -> None:
        thread = threading.Thread(target=self._run, name="camera-worker", daemon=True)
        thread.start()

    def reset_decoders(self) -> None:
        self.screen_decoder.reset()
        self.pulse_decoder.reset()
        self.state.last_message = ""
        self.state.last_payload_type = "text"
        self.state.last_image_bytes = b""
        self.state.last_image_name = ""
        self.state.last_image_size = 0
        self.state.last_error = ""
        self.state.pulse_bits_seen = 0
        self.state.screen_frames_seen = 0
        self.state.screen_decode_attempts = 0
        self.state.screen_crc_failures = 0
        self.state.screen_magic_failures = 0
        self.state.optical_frames_ok = 0
        self.state.frame_events.clear()
        self.state.decoder_status = "idle"
        self.state.log("decodificadores reiniciados")

    def _open_capture(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(self.state.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.state.camera_index)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self) -> None:
        last_camera = None
        frame_times: deque[float] = deque(maxlen=30)
        last_encode = 0.0
        preview_interval = 1.0 / 12.0
        while not self.stop_event.is_set():
            try:
                if self.capture is None or last_camera != self.state.camera_index:
                    if self.capture is not None:
                        self.capture.release()
                    self.capture = self._open_capture()
                    last_camera = self.state.camera_index
                    self.state.log(f"camara abierta index={last_camera}")

                ok, frame = self.capture.read()
                if not ok:
                    self.state.last_error = "No se pudo leer frame de la webcam"
                    time.sleep(0.15)
                    continue

                ts = time.time()
                frame_times.append(ts)
                if len(frame_times) >= 2:
                    span = frame_times[-1] - frame_times[0]
                    self.state.fps = (len(frame_times) - 1) / span if span > 0 else 0.0

                message: str | None = None
                warped = None
                if self.state.running:
                    if self.state.mode == "screen":
                        message, warped = self.screen_decoder.process(frame)
                    elif self.state.mode in {"flash", "ir"}:
                        message = self.pulse_decoder.process(frame, ts, self.state.mode)
                    if message is not None:
                        self.state.last_message = message
                        self.state.last_message_at = now_ms()

                if ts - last_encode >= preview_interval:
                    annotated = self._annotate(frame, warped)
                    ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 76])
                    if ok:
                        with self.lock:
                            self.jpeg = encoded.tobytes()
                    last_encode = ts
            except Exception as exc:  # Keep camera loop alive for field testing.
                self.state.last_error = str(exc)
                self.state.log(f"error: {exc}")
                time.sleep(0.5)

    def _annotate(self, frame: np.ndarray, warped: np.ndarray | None) -> np.ndarray:
        out = cv2.flip(frame, 1)
        height, width = out.shape[:2]
        if self.state.mode in {"flash", "ir"}:
            side = int(min(width, height) * 0.36)
            x0 = (width - side) // 2
            y0 = (height - side) // 2
            cv2.rectangle(out, (x0, y0), (x0 + side, y0 + side), (0, 220, 255), 2)
        else:
            if self.screen_decoder.last_panel_box is not None:
                x, y, panel_w, panel_h = self.screen_decoder.last_panel_box
                x0 = width - (x + panel_w)
                y0 = y
            else:
                panel_h = int(height * 0.62)
                panel_w = int(panel_h * (self.screen_decoder.grid_cols / self.screen_decoder.grid_rows))
                if panel_w > int(width * 0.48):
                    panel_w = int(width * 0.48)
                    panel_h = int(panel_w * (self.screen_decoder.grid_rows / self.screen_decoder.grid_cols))
                x0 = (width - panel_w) // 2
                y0 = (height - panel_h) // 2
            cv2.rectangle(out, (x0, y0), (x0 + panel_w, y0 + panel_h), (80, 220, 80), 2)

        text = f"mode={self.state.mode} fps={self.state.fps:.1f} {self.state.decoder_status}"
        cv2.rectangle(out, (0, 0), (width, 34), (20, 22, 26), -1)
        cv2.putText(out, text, (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (240, 240, 240), 2)

        if warped is not None:
            thumb_w = 90
            thumb_h = 180
            thumb = cv2.resize(warped, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            y0 = max(0, height - thumb_h - 10)
            x0 = max(0, width - thumb_w - 10)
            out[y0 : y0 + thumb_h, x0 : x0 + thumb_w] = thumb
            cv2.rectangle(out, (x0, y0), (x0 + thumb_w, y0 + thumb_h), (255, 255, 255), 1)
        return out

    def get_jpeg(self) -> bytes:
        with self.lock:
            return self.jpeg


state = ReceiverState()
worker = CameraWorker(state)


class Handler(BaseHTTPRequestHandler):
    server_version = "OpticalLinkReceiver/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
        elif parsed.path == "/static/styles.css":
            self._send_file(STATIC / "styles.css", "text/css; charset=utf-8")
        elif parsed.path == "/static/app.js":
            self._send_file(STATIC / "app.js", "application/javascript; charset=utf-8")
        elif parsed.path == "/video":
            self._video_stream()
        elif parsed.path == "/api/status":
            self._send_json(self._status())
        elif parsed.path == "/received/latest-image":
            if not state.last_image_bytes:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(state.last_image_bytes)))
            self.end_headers()
            self.wfile.write(state.last_image_bytes)
        elif parsed.path == "/received/latest-file":
            if not state.last_file_bytes:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{state.last_file_name or "received.bin"}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(state.last_file_bytes)))
            self.end_headers()
            self.wfile.write(state.last_file_bytes)
        elif parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            body = {}

        if parsed.path == "/api/config":
            mode = body.get("mode")
            if mode in {"screen", "flash", "ir"} and mode != state.mode:
                state.mode = mode
                worker.reset_decoders()
                state.log(f"modo cambiado a {mode}")
            if state.tracking_mode != "center":
                state.tracking_mode = "center"
                worker.reset_decoders()
                state.log("tracking cambiado a center")
            grid_cols = body.get("grid_cols")
            grid_rows = body.get("grid_rows")
            if isinstance(grid_cols, int) and isinstance(grid_rows, int):
                grid_cols = max(ScreenGridDecoder.MIN_GRID_COLS, min(ScreenGridDecoder.MAX_GRID_COLS, grid_cols))
                grid_rows = max(ScreenGridDecoder.MIN_GRID_ROWS, min(ScreenGridDecoder.MAX_GRID_ROWS, grid_rows))
                if grid_cols != state.grid_cols or grid_rows != state.grid_rows:
                    state.grid_cols = grid_cols
                    state.grid_rows = grid_rows
                    worker.reset_decoders()
                    state.log(f"grid cambiada a {grid_cols}x{grid_rows}")
            camera_index = body.get("camera_index")
            if isinstance(camera_index, int) and 0 <= camera_index <= 8:
                state.camera_index = camera_index
            if "running" in body:
                state.running = bool(body["running"])
            self._send_json({"ok": True, **self._status()})
        elif parsed.path == "/api/reset":
            worker.reset_decoders()
            self._send_json({"ok": True, **self._status()})
        elif parsed.path == "/api/shutdown":
            self._send_json({"ok": True, "shutdown": True})
            state.log("apagado solicitado desde web")
            threading.Timer(0.35, lambda: os._exit(0)).start()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _video_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        while True:
            jpeg = worker.get_jpeg()
            if not jpeg:
                time.sleep(0.05)
                continue
            try:
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError):
                break

    @staticmethod
    def _status() -> dict[str, Any]:
        return {
            "mode": state.mode,
            "camera_index": state.camera_index,
            "running": state.running,
            "tracking_mode": state.tracking_mode,
            "last_message": state.last_message,
            "last_message_at": state.last_message_at,
            "last_payload_type": state.last_payload_type,
            "last_image_name": state.last_image_name,
            "last_image_size": state.last_image_size,
            "last_image_url": "/received/latest-image" if state.last_image_bytes else "",
            "last_file_name": state.last_file_name,
            "last_file_size": state.last_file_size,
            "last_file_url": "/received/latest-file" if state.last_file_bytes else "",
            "last_error": state.last_error,
            "fps": round(state.fps, 1),
            "brightness": round(state.brightness, 1),
            "threshold": round(state.threshold, 1),
            "decoder_status": state.decoder_status,
            "screen_frames_seen": state.screen_frames_seen,
            "screen_decode_attempts": state.screen_decode_attempts,
            "screen_crc_failures": state.screen_crc_failures,
            "screen_magic_failures": state.screen_magic_failures,
            "optical_frames_ok": state.optical_frames_ok,
            "pulse_bits_seen": state.pulse_bits_seen,
            "grid_cols": state.grid_cols,
            "grid_rows": state.grid_rows,
            "frame_bytes": worker.screen_decoder.frame_bytes,
            "chunk_size": worker.screen_decoder.chunk_size,
            "logs": list(state.logs),
            "frame_events": list(state.frame_events),
        }


def main() -> None:
    port = int(os.environ.get("OPTICAL_LINK_PORT", "8000"))
    worker.start()
    state.log("receptor iniciado")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Optical Link Receiver: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        worker.stop_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
