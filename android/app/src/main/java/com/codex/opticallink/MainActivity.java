package com.codex.opticallink;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.hardware.ConsumerIrManager;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.OpenableColumns;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.zip.Deflater;

public class MainActivity extends Activity {
    private static final int REQUEST_CAMERA = 10;
    private static final int REQUEST_IMAGE = 20;
    private static final int MODE_SCREEN = 0;
    private static final int MODE_FLASH = 1;
    private static final int MODE_IR = 2;
    private static final int DEFAULT_GRID_COLS = 25;
    private static final int DEFAULT_GRID_ROWS = 50;
    private static final int MIN_GRID_COLS = 12;
    private static final int MAX_GRID_COLS = 60;
    private static final int MIN_GRID_ROWS = 12;
    private static final int MAX_GRID_ROWS = 80;
    private static final int MARKER_CELLS = 3;
    private static final int CALIBRATION_CELLS = 8;
    private static final int SCREEN_MIN_INTERVAL_MS = 50;
    private static final int SCREEN_MAX_INTERVAL_MS = 1000;
    private static final int SCREEN_INTERVAL_STEP_MS = 25;
    private static final int SCREEN_START_DELAY_MS = 2000;
    private static final int[] COLOR_PALETTE = new int[] {
        Color.rgb(0, 0, 0),
        Color.rgb(0, 0, 255),
        Color.rgb(0, 255, 0),
        Color.rgb(0, 255, 255),
        Color.rgb(255, 0, 0),
        Color.rgb(255, 0, 255),
        Color.rgb(255, 255, 0),
        Color.rgb(255, 255, 255)
    };

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Random random = new Random();
    private EditText messageInput;
    private EditText gridColsInput;
    private EditText gridRowsInput;
    private RadioGroup modeGroup;
    private TextView statusView;
    private TextView speedLabel;
    private TextView payloadInfoView;
    private int screenFrameMs = 200;
    private int gridCols = DEFAULT_GRID_COLS;
    private int gridRows = DEFAULT_GRID_ROWS;
    private String lastText = "hola";
    private byte[] selectedImagePayload;
    private int selectedImageOriginalBytes;
    private int selectedImageCompressedBytes;
    private String selectedImageName = "";
    private boolean restoringUi;
    private volatile boolean transmitting;
    private CameraManager cameraManager;
    private String torchCameraId;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        cameraManager = (CameraManager) getSystemService(Context.CAMERA_SERVICE);
        torchCameraId = findTorchCameraId();
        showMainUi();
        requestCameraPermissionIfNeeded();
    }

    private void requestCameraPermissionIfNeeded() {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] { Manifest.permission.CAMERA }, REQUEST_CAMERA);
        }
    }

    private void showMainUi() {
        transmitting = false;
        setTorch(false);
        Window window = getWindow();
        window.clearFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        window.getDecorView().setSystemUiVisibility(0);

        ScrollView scrollView = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18), dp(18), dp(18), dp(18));
        root.setBackgroundColor(Color.rgb(245, 247, 251));
        scrollView.addView(root);

        TextView title = new TextView(this);
        title.setText("Optical Link");
        title.setTextColor(Color.rgb(24, 32, 47));
        title.setTextSize(26);
        title.setGravity(Gravity.START);
        title.setTypeface(null, 1);
        root.addView(title);

        TextView subtitle = new TextView(this);
        subtitle.setText("Movil a PC por camara: pantalla, linterna o infrarrojos");
        subtitle.setTextColor(Color.rgb(102, 112, 133));
        subtitle.setTextSize(14);
        subtitle.setPadding(0, dp(5), 0, dp(18));
        root.addView(subtitle);

        messageInput = new EditText(this);
        messageInput.setTextColor(Color.rgb(24, 32, 47));
        messageInput.setHintTextColor(Color.rgb(152, 162, 179));
        messageInput.setHint("Escribe una palabra o frase corta");
        restoringUi = true;
        messageInput.setText(lastText);
        restoringUi = false;
        messageInput.setMinLines(3);
        messageInput.setGravity(Gravity.TOP | Gravity.START);
        messageInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        messageInput.setBackgroundColor(Color.WHITE);
        messageInput.setPadding(dp(12), dp(10), dp(12), dp(10));
        messageInput.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                lastText = s.toString();
                if (restoringUi) {
                    return;
                }
                selectedImagePayload = null;
                selectedImageName = "";
                selectedImageOriginalBytes = 0;
                selectedImageCompressedBytes = 0;
                updatePayloadInfo();
            }

            @Override
            public void afterTextChanged(Editable s) {
            }
        });
        root.addView(messageInput, new LinearLayout.LayoutParams(-1, dp(112)));

        Button imageButton = new Button(this);
        imageButton.setText("Seleccionar imagen/PDF/archivo");
        imageButton.setTextSize(15);
        imageButton.setAllCaps(false);
        imageButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                pickImage();
            }
        });
        LinearLayout.LayoutParams imageParams = new LinearLayout.LayoutParams(-1, dp(48));
        imageParams.setMargins(0, dp(10), 0, 0);
        root.addView(imageButton, imageParams);

        Button clearImageButton = new Button(this);
        clearImageButton.setText("Volver a enviar texto");
        clearImageButton.setTextSize(15);
        clearImageButton.setAllCaps(false);
        clearImageButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                selectedImagePayload = null;
                selectedImageName = "";
                selectedImageOriginalBytes = 0;
                selectedImageCompressedBytes = 0;
                updatePayloadInfo();
            }
        });
        LinearLayout.LayoutParams clearImageParams = new LinearLayout.LayoutParams(-1, dp(46));
        clearImageParams.setMargins(0, dp(8), 0, 0);
        root.addView(clearImageButton, clearImageParams);

        payloadInfoView = new TextView(this);
        payloadInfoView.setTextColor(Color.rgb(102, 112, 133));
        payloadInfoView.setTextSize(13);
        payloadInfoView.setPadding(0, dp(10), 0, 0);
        root.addView(payloadInfoView);

        modeGroup = new RadioGroup(this);
        modeGroup.setOrientation(RadioGroup.VERTICAL);
        modeGroup.setPadding(0, dp(14), 0, dp(14));
        addModeButton("Pantalla grid color", MODE_SCREEN, true);
        addModeButton("Linterna por pulsos lentos", MODE_FLASH, false);
        addModeButton("Infrarrojos Xiaomi", MODE_IR, false);
        root.addView(modeGroup);

        LinearLayout gridRow = new LinearLayout(this);
        gridRow.setOrientation(LinearLayout.HORIZONTAL);
        gridRow.setPadding(0, 0, 0, dp(10));
        gridColsInput = buildNumberInput(String.valueOf(gridCols), "Columnas");
        gridRowsInput = buildNumberInput(String.valueOf(gridRows), "Filas");
        gridRow.addView(gridColsInput, new LinearLayout.LayoutParams(0, dp(52), 1));
        LinearLayout.LayoutParams rowsParams = new LinearLayout.LayoutParams(0, dp(52), 1);
        rowsParams.setMargins(dp(10), 0, 0, 0);
        gridRow.addView(gridRowsInput, rowsParams);
        root.addView(gridRow);

        speedLabel = new TextView(this);
        speedLabel.setTextColor(Color.rgb(15, 118, 110));
        speedLabel.setTextSize(14);
        speedLabel.setPadding(0, dp(2), 0, dp(8));
        root.addView(speedLabel);

        SeekBar speedSlider = new SeekBar(this);
        speedSlider.setMax((SCREEN_MAX_INTERVAL_MS - SCREEN_MIN_INTERVAL_MS) / SCREEN_INTERVAL_STEP_MS);
        speedSlider.setProgress((screenFrameMs - SCREEN_MIN_INTERVAL_MS) / SCREEN_INTERVAL_STEP_MS);
        speedSlider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar seekBar, int progress, boolean fromUser) {
                screenFrameMs = SCREEN_MIN_INTERVAL_MS + progress * SCREEN_INTERVAL_STEP_MS;
                updateSpeedLabel();
            }

            @Override
            public void onStartTrackingTouch(SeekBar seekBar) {
            }

            @Override
            public void onStopTrackingTouch(SeekBar seekBar) {
            }
        });
        root.addView(speedSlider, new LinearLayout.LayoutParams(-1, dp(48)));
        updateSpeedLabel();
        updatePayloadInfo();

        Button sendButton = new Button(this);
        sendButton.setText("Enviar");
        sendButton.setTextSize(16);
        sendButton.setAllCaps(false);
        sendButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                startTransmission();
            }
        });
        root.addView(sendButton, new LinearLayout.LayoutParams(-1, dp(52)));

        Button stopButton = new Button(this);
        stopButton.setText("Parar transmision");
        stopButton.setTextSize(16);
        stopButton.setAllCaps(false);
        stopButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                transmitting = false;
                setTorch(false);
                setStatus("Transmision parada");
            }
        });
        LinearLayout.LayoutParams stopParams = new LinearLayout.LayoutParams(-1, dp(48));
        stopParams.setMargins(0, dp(10), 0, 0);
        root.addView(stopButton, stopParams);

        statusView = new TextView(this);
        statusView.setTextColor(Color.rgb(15, 118, 110));
        statusView.setTextSize(14);
        statusView.setPadding(0, dp(18), 0, 0);
        statusView.setText("Listo. Apunta la webcam al movil antes de enviar.");
        root.addView(statusView);

        TextView notes = new TextView(this);
        notes.setTextColor(Color.rgb(102, 112, 133));
        notes.setTextSize(13);
        notes.setPadding(0, dp(18), 0, 0);
        notes.setText(
            "Pantalla: llena la webcam con el cuadrado.\n" +
            "Linterna: apunta la luz al centro del recuadro amarillo.\n" +
            "IR: apunta el emisor superior del Xiaomi a la webcam; puede depender del filtro IR del portatil."
        );
        root.addView(notes);

        setContentView(scrollView);
    }

    private void addModeButton(String label, int id, boolean checked) {
        RadioButton button = new RadioButton(this);
        button.setId(id);
        button.setText(label);
        button.setTextColor(Color.rgb(24, 32, 47));
        button.setTextSize(16);
        button.setPadding(0, dp(5), 0, dp(5));
        modeGroup.addView(button);
        if (checked) {
            button.setChecked(true);
        }
    }

    private EditText buildNumberInput(String value, String hint) {
        EditText input = new EditText(this);
        input.setText(value);
        input.setHint(hint);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_NUMBER);
        input.setTextColor(Color.rgb(24, 32, 47));
        input.setHintTextColor(Color.rgb(152, 162, 179));
        input.setBackgroundColor(Color.WHITE);
        input.setPadding(dp(12), 0, dp(12), 0);
        input.addTextChangedListener(new TextWatcher() {
            @Override
            public void beforeTextChanged(CharSequence s, int start, int count, int after) {
            }

            @Override
            public void onTextChanged(CharSequence s, int start, int before, int count) {
                syncGridInputs();
                updatePayloadInfo();
            }

            @Override
            public void afterTextChanged(Editable s) {
            }
        });
        return input;
    }

    private void updateSpeedLabel() {
        if (speedLabel != null) {
            float framesPerSecond = 1000f / Math.max(1, screenFrameMs);
            speedLabel.setText(String.format(Locale.US, "Pantalla: %d ms por trama (%.1f tramas/s)", screenFrameMs, framesPerSecond));
        }
        updatePayloadInfo();
    }

    private void updatePayloadInfo() {
        if (payloadInfoView == null) {
            return;
        }
        syncGridInputs();
        byte[] payload = selectedImagePayload != null ? selectedImagePayload : buildTextPayload(lastText);
        TransmissionEstimate estimate = estimatePayload(payload);
        if (selectedImagePayload != null) {
            payloadInfoView.setText(
                "Archivo: " + selectedImageName + "\n" +
                "Original: " + formatBytes(selectedImageOriginalBytes) + " | preparado: " + formatBytes(selectedImageCompressedBytes) + "\n" +
                "Grid: " + gridCols + "x" + gridRows + " | tramas: " + estimate.frames + " | estimado: " + formatSeconds(estimate.seconds)
            );
        } else {
            int textBytes = lastText.getBytes(StandardCharsets.UTF_8).length;
            payloadInfoView.setText(
                "Texto UTF-8: " + formatBytes(textBytes) + " | envio: " + formatBytes(estimate.encodedBytes) + "\n" +
                "Grid: " + gridCols + "x" + gridRows + " | tramas: " + estimate.frames + " | estimado: " + formatSeconds(estimate.seconds)
            );
        }
    }

    private void syncGridInputs() {
        gridCols = readBoundedInt(gridColsInput, gridCols, MIN_GRID_COLS, MAX_GRID_COLS);
        gridRows = readBoundedInt(gridRowsInput, gridRows, MIN_GRID_ROWS, MAX_GRID_ROWS);
    }

    private int readBoundedInt(EditText input, int fallback, int min, int max) {
        if (input == null) {
            return fallback;
        }
        try {
            int value = Integer.parseInt(input.getText().toString().trim());
            return Math.max(min, Math.min(max, value));
        } catch (NumberFormatException ex) {
            return fallback;
        }
    }

    private int screenFrameBytes() {
        int symbols = Math.max(0, gridCols * gridRows - CALIBRATION_CELLS);
        return Math.max(32, (symbols * 3) / 8);
    }

    private int screenChunkSize() {
        return Math.max(1, screenFrameBytes() - 16);
    }

    private void pickImage() {
        Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
        intent.setType("*/*");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(Intent.createChooser(intent, "Selecciona archivo"), REQUEST_IMAGE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == REQUEST_IMAGE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            loadSelectedFile(data.getData());
        }
    }

    private void loadSelectedFile(Uri uri) {
        try {
            byte[] original = readAllBytes(uri);
            selectedImageOriginalBytes = original.length;
            selectedImageName = getDisplayName(uri);
            if (selectedImageName.length() == 0) {
                selectedImageName = "archivo.bin";
            }

            Bitmap bitmap = BitmapFactory.decodeByteArray(original, 0, original.length);
            if (bitmap != null) {
                Bitmap scaled = scaleBitmap(bitmap, 520);
                ByteArrayOutputStream jpeg = new ByteArrayOutputStream();
                scaled.compress(Bitmap.CompressFormat.JPEG, 42, jpeg);
                byte[] compressed = jpeg.toByteArray();
                selectedImageCompressedBytes = compressed.length;
                selectedImagePayload = buildImagePayload(compressed, selectedImageName, selectedImageOriginalBytes);
            } else {
                selectedImageCompressedBytes = original.length;
                selectedImagePayload = buildFilePayload(original, selectedImageName, selectedImageOriginalBytes);
            }
            updatePayloadInfo();
            Toast.makeText(this, "Archivo preparado", Toast.LENGTH_SHORT).show();
        } catch (IOException exc) {
            Toast.makeText(this, "Error leyendo imagen: " + exc.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private byte[] readAllBytes(Uri uri) throws IOException {
        InputStream input = getContentResolver().openInputStream(uri);
        if (input == null) {
            throw new IOException("sin stream");
        }
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        } finally {
            input.close();
        }
    }

    private String getDisplayName(Uri uri) {
        Cursor cursor = null;
        try {
            cursor = getContentResolver().query(uri, null, null, null, null);
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    return cursor.getString(index);
                }
            }
        } catch (Exception ignored) {
        } finally {
            if (cursor != null) {
                cursor.close();
            }
        }
        return "imagen.jpg";
    }

    private Bitmap scaleBitmap(Bitmap bitmap, int maxSide) {
        int width = bitmap.getWidth();
        int height = bitmap.getHeight();
        int longest = Math.max(width, height);
        if (longest <= maxSide) {
            return bitmap;
        }
        float scale = maxSide / (float) longest;
        int targetW = Math.max(1, Math.round(width * scale));
        int targetH = Math.max(1, Math.round(height * scale));
        return Bitmap.createScaledBitmap(bitmap, targetW, targetH, true);
    }

    private byte[] buildTextPayload(String text) {
        byte[] textBytes = text.getBytes(StandardCharsets.UTF_8);
        byte[] payload = new byte[textBytes.length + 4];
        payload[0] = 'T';
        payload[1] = 'X';
        payload[2] = 'T';
        payload[3] = '1';
        System.arraycopy(textBytes, 0, payload, 4, textBytes.length);
        return payload;
    }

    private byte[] buildImagePayload(byte[] jpeg, String name, int originalSize) {
        byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
        int nameLen = Math.min(nameBytes.length, 180);
        byte[] payload = new byte[10 + nameLen + jpeg.length];
        payload[0] = 'I';
        payload[1] = 'M';
        payload[2] = 'G';
        payload[3] = '1';
        payload[4] = (byte) ((originalSize >> 24) & 0xFF);
        payload[5] = (byte) ((originalSize >> 16) & 0xFF);
        payload[6] = (byte) ((originalSize >> 8) & 0xFF);
        payload[7] = (byte) (originalSize & 0xFF);
        payload[8] = (byte) ((nameLen >> 8) & 0xFF);
        payload[9] = (byte) (nameLen & 0xFF);
        System.arraycopy(nameBytes, 0, payload, 10, nameLen);
        System.arraycopy(jpeg, 0, payload, 10 + nameLen, jpeg.length);
        return payload;
    }

    private byte[] buildFilePayload(byte[] bytes, String name, int originalSize) {
        byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
        int nameLen = Math.min(nameBytes.length, 180);
        byte[] payload = new byte[10 + nameLen + bytes.length];
        payload[0] = 'F';
        payload[1] = 'I';
        payload[2] = 'L';
        payload[3] = '1';
        payload[4] = (byte) ((originalSize >> 24) & 0xFF);
        payload[5] = (byte) ((originalSize >> 16) & 0xFF);
        payload[6] = (byte) ((originalSize >> 8) & 0xFF);
        payload[7] = (byte) (originalSize & 0xFF);
        payload[8] = (byte) ((nameLen >> 8) & 0xFF);
        payload[9] = (byte) (nameLen & 0xFF);
        System.arraycopy(nameBytes, 0, payload, 10, nameLen);
        System.arraycopy(bytes, 0, payload, 10 + nameLen, bytes.length);
        return payload;
    }

    private TransmissionEstimate estimatePayload(byte[] payload) {
        byte[] compressed = compressBytes(payload);
        int encodedBytes = compressed.length > 0 && compressed.length < payload.length ? compressed.length : payload.length;
        int chunkSize = screenChunkSize();
        int frames = Math.max(1, (encodedBytes + chunkSize - 1) / chunkSize);
        float seconds = SCREEN_START_DELAY_MS / 1000f + (frames * screenFrameMs / 1000f);
        return new TransmissionEstimate(encodedBytes, frames, seconds);
    }

    private String formatBytes(int bytes) {
        if (bytes >= 1024 * 1024) {
            return String.format(Locale.US, "%.2f MB", bytes / (1024f * 1024f));
        }
        if (bytes >= 1024) {
            return String.format(Locale.US, "%.1f KB", bytes / 1024f);
        }
        return bytes + " B";
    }

    private String formatSeconds(float seconds) {
        if (seconds >= 60f) {
            return String.format(Locale.US, "%.1f min", seconds / 60f);
        }
        return String.format(Locale.US, "%.1f s", seconds);
    }

    private void startTransmission() {
        lastText = messageInput.getText().toString();
        byte[] screenPayload = selectedImagePayload != null ? selectedImagePayload : buildTextPayload(lastText);
        if (screenPayload.length == 4) {
            Toast.makeText(this, "Escribe algo primero", Toast.LENGTH_SHORT).show();
            return;
        }

        int selected = modeGroup.getCheckedRadioButtonId();
        if (selected == MODE_SCREEN) {
            startScreenTransmission(screenPayload);
        } else if (selected == MODE_FLASH) {
            startFlashTransmission(lastText);
        } else if (selected == MODE_IR) {
            startIrTransmission(lastText);
        }
    }

    private void startScreenTransmission(byte[] payload) {
        syncGridInputs();
        List<byte[]> frames = buildScreenFrames(payload);
        transmitting = true;
        ScreenGridView view = new ScreenGridView(this, frames, screenFrameMs, gridCols, gridRows);
        view.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View view, MotionEvent event) {
                if (event.getAction() == MotionEvent.ACTION_UP) {
                    transmitting = false;
                    showMainUi();
                }
                return true;
            }
        });
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        );
        setContentView(view);
        setStatus("Transmitiendo por pantalla");
    }

    private void startFlashTransmission(String message) {
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] { Manifest.permission.CAMERA }, REQUEST_CAMERA);
            return;
        }
        if (torchCameraId == null) {
            Toast.makeText(this, "No he encontrado linterna disponible", Toast.LENGTH_LONG).show();
            return;
        }
        byte[] frame = buildPulseFrame(message, true);
        final List<Integer> bits = bytesToBits(frame);
        transmitting = true;
        setStatus(String.format(Locale.US, "Linterna: %d bits, aprox %.0f s", bits.size(), bits.size() * 0.90));
        new Thread(new Runnable() {
            @Override
            public void run() {
                transmitTorchBits(bits);
            }
        }, "torch-transmitter").start();
    }

    private void startIrTransmission(String message) {
        final ConsumerIrManager ir = (ConsumerIrManager) getSystemService(Context.CONSUMER_IR_SERVICE);
        if (ir == null || !ir.hasIrEmitter()) {
            Toast.makeText(this, "Este movil no expone emisor IR a Android", Toast.LENGTH_LONG).show();
            return;
        }
        byte[] frame = buildPulseFrame(message, false);
        List<Integer> bits = bytesToBits(frame);
        final int[] pattern = buildIrPattern(bits);
        transmitting = true;
        setStatus(String.format(Locale.US, "IR: %d bits, patron %.1f s", bits.size(), sumMicros(pattern) / 1_000_000.0));
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    ir.transmit(38000, pattern);
                } catch (final RuntimeException ex) {
                    mainHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            Toast.makeText(MainActivity.this, "Fallo IR: " + ex.getMessage(), Toast.LENGTH_LONG).show();
                        }
                    });
                } finally {
                    transmitting = false;
                }
            }
        }, "ir-transmitter").start();
    }

    private void transmitTorchBits(List<Integer> bits) {
        try {
            long next = SystemClock.elapsedRealtime();
            setTorch(true);
            next += 1200;
            waitUntil(next);
            setTorch(false);
            next += 900;
            waitUntil(next);
            for (int bit : bits) {
                if (!transmitting) {
                    break;
                }
                if (bit == 1) {
                    setTorch(true);
                    next += 280;
                    waitUntil(next);
                    setTorch(false);
                    next += 620;
                    waitUntil(next);
                } else {
                    setTorch(false);
                    next += 620;
                    waitUntil(next);
                    setTorch(true);
                    next += 280;
                    waitUntil(next);
                }
            }
        } finally {
            setTorch(false);
            transmitting = false;
            mainHandler.post(new Runnable() {
                @Override
                public void run() {
                    setStatus("Linterna finalizada");
                }
            });
        }
    }

    private List<byte[]> buildScreenFrames(byte[] rawPayload) {
        byte[] compressedPayload = compressBytes(rawPayload);
        boolean compressed = compressedPayload.length > 0 && compressedPayload.length < rawPayload.length;
        byte[] payload = compressed ? compressedPayload : rawPayload;
        int frameBytes = screenFrameBytes();
        int chunkSize = screenChunkSize();
        int total = Math.max(1, (payload.length + chunkSize - 1) / chunkSize);
        int txId = random.nextInt(256);
        List<byte[]> frames = new ArrayList<>();
        for (int seq = 0; seq < total; seq++) {
            byte[] frame = new byte[frameBytes];
            frame[0] = 'O';
            frame[1] = 'C';
            frame[2] = 3;
            frame[3] = (byte) (compressed ? 1 : 0);
            frame[4] = (byte) txId;
            frame[5] = (byte) ((seq >> 8) & 0xFF);
            frame[6] = (byte) (seq & 0xFF);
            frame[7] = (byte) ((total >> 8) & 0xFF);
            frame[8] = (byte) (total & 0xFF);
            int start = seq * chunkSize;
            int len = Math.max(0, Math.min(chunkSize, payload.length - start));
            frame[9] = (byte) ((len >> 8) & 0xFF);
            frame[10] = (byte) (len & 0xFF);
            int originalLen = Math.min(rawPayload.length, 65535);
            frame[11] = (byte) ((originalLen >> 8) & 0xFF);
            frame[12] = (byte) (originalLen & 0xFF);
            frame[13] = 0;
            if (len > 0) {
                System.arraycopy(payload, start, frame, 14, len);
            }
            for (int i = 14 + len; i < frameBytes - 2; i++) {
                frame[i] = (byte) ((i * 73 + seq * 17 + txId * 31) & 0xFF);
            }
            int crc = crc16(frame, 0, frameBytes - 2);
            frame[frameBytes - 2] = (byte) ((crc >> 8) & 0xFF);
            frame[frameBytes - 1] = (byte) (crc & 0xFF);
            frames.add(frame);
        }
        return frames;
    }

    private byte[] compressBytes(byte[] input) {
        if (input.length < 24) {
            return new byte[0];
        }
        Deflater deflater = new Deflater(Deflater.BEST_SPEED);
        deflater.setInput(input);
        deflater.finish();
        byte[] buffer = new byte[input.length + 64];
        int length = deflater.deflate(buffer);
        deflater.end();
        if (length <= 0) {
            return new byte[0];
        }
        byte[] out = new byte[length];
        System.arraycopy(buffer, 0, out, 0, length);
        return out;
    }

    private byte[] buildPulseFrame(String message, boolean flash) {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        int len = Math.min(payload.length, 180);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write('O');
        out.write(flash ? 'L' : 'I');
        out.write(1);
        out.write(len);
        out.write(payload, 0, len);
        byte[] withoutCrc = out.toByteArray();
        int crc = crc16(withoutCrc, 0, withoutCrc.length);
        out.write((crc >> 8) & 0xFF);
        out.write(crc & 0xFF);
        return out.toByteArray();
    }

    private int[] buildIrPattern(List<Integer> bits) {
        IrPattern pattern = new IrPattern();
        pattern.add(true, 500_000);
        pattern.add(false, 420_000);
        for (int bit : bits) {
            if (bit == 1) {
                pattern.add(true, 180_000);
                pattern.add(false, 440_000);
            } else {
                pattern.add(false, 440_000);
                pattern.add(true, 180_000);
            }
        }
        pattern.add(false, 200_000);
        return pattern.toArray();
    }

    private String findTorchCameraId() {
        try {
            for (String id : cameraManager.getCameraIdList()) {
                CameraCharacteristics characteristics = cameraManager.getCameraCharacteristics(id);
                Boolean hasFlash = characteristics.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
                Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
                if (Boolean.TRUE.equals(hasFlash)
                    && facing != null
                    && facing == CameraCharacteristics.LENS_FACING_BACK) {
                    return id;
                }
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    private void setTorch(boolean enabled) {
        if (cameraManager == null || torchCameraId == null) {
            return;
        }
        try {
            cameraManager.setTorchMode(torchCameraId, enabled);
        } catch (Exception ignored) {
        }
    }

    private void setStatus(String value) {
        if (statusView != null) {
            statusView.setText(value);
        }
    }

    private void sleepMs(long ms) {
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
        }
    }

    private void waitUntil(long targetMs) {
        while (transmitting) {
            long remaining = targetMs - SystemClock.elapsedRealtime();
            if (remaining <= 0) {
                return;
            }
            sleepMs(Math.min(remaining, 50));
        }
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }

    private static int crc16(byte[] data, int offset, int length) {
        int crc = 0xFFFF;
        for (int i = offset; i < offset + length; i++) {
            crc ^= (data[i] & 0xFF) << 8;
            for (int bit = 0; bit < 8; bit++) {
                if ((crc & 0x8000) != 0) {
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF;
                } else {
                    crc = (crc << 1) & 0xFFFF;
                }
            }
        }
        return crc & 0xFFFF;
    }

    private static List<Integer> bytesToBits(byte[] data) {
        List<Integer> bits = new ArrayList<>();
        for (byte b : data) {
            int value = b & 0xFF;
            for (int shift = 7; shift >= 0; shift--) {
                bits.add((value >> shift) & 1);
            }
        }
        return bits;
    }

    private static long sumMicros(int[] pattern) {
        long total = 0;
        for (int value : pattern) {
            total += value;
        }
        return total;
    }

    private static final class TransmissionEstimate {
        final int encodedBytes;
        final int frames;
        final float seconds;

        TransmissionEstimate(int encodedBytes, int frames, float seconds) {
            this.encodedBytes = encodedBytes;
            this.frames = frames;
            this.seconds = seconds;
        }
    }

    private final class ScreenGridView extends View {
        private final List<int[]> colorFrames = new ArrayList<>();
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final int frameIntervalMs;
        private final int cols;
        private final int rows;
        private final long startAtMs;
        private int index;

        ScreenGridView(Context context, List<byte[]> frames, int frameIntervalMs, int cols, int rows) {
            super(context);
            this.frameIntervalMs = Math.max(SCREEN_MIN_INTERVAL_MS, Math.min(SCREEN_MAX_INTERVAL_MS, frameIntervalMs));
            this.cols = cols;
            this.rows = rows;
            this.startAtMs = SystemClock.uptimeMillis() + SCREEN_START_DELAY_MS;
            setKeepScreenOn(true);
            setBackgroundColor(Color.BLACK);
            setFocusable(true);
            for (byte[] frame : frames) {
                colorFrames.add(toColorArray(frame));
            }
            mainHandler.postDelayed(tick, 80);
        }

        private final Runnable tick = new Runnable() {
            @Override
            public void run() {
                if (!transmitting) {
                    return;
                }
                long now = SystemClock.uptimeMillis();
                if (now >= startAtMs) {
                    index = (index + 1) % Math.max(1, colorFrames.size());
                    mainHandler.postDelayed(this, frameIntervalMs);
                } else {
                    mainHandler.postDelayed(this, 80);
                }
                invalidate();
            }
        };

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            int width = getWidth();
            int height = getHeight();
            int gridWidth = width;
            int gridHeight = (int) (gridWidth * (rows / (float) cols));
            if (gridHeight > height) {
                gridHeight = height;
                gridWidth = (int) (gridHeight * (cols / (float) rows));
            }
            int left = (width - gridWidth) / 2;
            int top = (height - gridHeight) / 2;
            long remaining = startAtMs - SystemClock.uptimeMillis();
            if (remaining > 0) {
                paint.setStyle(Paint.Style.FILL);
                paint.setColor(Color.WHITE);
                paint.setTextAlign(Paint.Align.CENTER);
                paint.setTextSize(dp(30));
                canvas.drawText("Coloca la pantalla", width / 2f, height / 2f - dp(18), paint);
                paint.setTextSize(dp(20));
                canvas.drawText(String.format(Locale.US, "%.1f s", remaining / 1000f), width / 2f, height / 2f + dp(22), paint);
                return;
            }

            int[] colors = colorFrames.get(index);
            float cellW = gridWidth / (float) cols;
            float cellH = gridHeight / (float) rows;
            float gap = 0f;
            for (int row = 0; row < rows; row++) {
                for (int col = 0; col < cols; col++) {
                    int colorIndex = colors[row * cols + col];
                    paint.setColor(COLOR_PALETTE[Math.floorMod(colorIndex, COLOR_PALETTE.length)]);
                    float x0 = left + col * cellW + gap;
                    float y0 = top + row * cellH + gap;
                    canvas.drawRect(x0, y0, x0 + cellW + 0.5f, y0 + cellH + 0.5f, paint);
                }
            }
        }

        private int[] toColorArray(byte[] data) {
            int[] colors = new int[cols * rows];
            for (int i = 0; i < CALIBRATION_CELLS; i++) {
                colors[i] = i;
            }
            int p = CALIBRATION_CELLS;
            int pending = 0;
            int pendingBits = 0;
            for (byte value : data) {
                int unsigned = value & 0xFF;
                for (int shift = 7; shift >= 0; shift--) {
                    pending = (pending << 1) | ((unsigned >> shift) & 1);
                    pendingBits++;
                    if (pendingBits == 3 && p < colors.length) {
                        colors[p++] = pending & 7;
                        pending = 0;
                        pendingBits = 0;
                    }
                }
            }
            while (p < colors.length) {
                colors[p] = ((p * 5) + 3) & 7;
                p++;
            }
            return colors;
        }
    }

    private static final class IrPattern {
        private final List<Integer> values = new ArrayList<>();
        private boolean currentOn = true;

        void add(boolean on, int micros) {
            if (micros <= 0) {
                return;
            }
            if (values.isEmpty()) {
                if (!on) {
                    values.add(1);
                    currentOn = false;
                }
                values.add(micros);
                currentOn = !on;
                return;
            }
            boolean previousState = !currentOn;
            if (previousState == on) {
                int last = values.size() - 1;
                values.set(last, values.get(last) + micros);
            } else {
                values.add(micros);
                currentOn = !currentOn;
            }
        }

        int[] toArray() {
            int[] out = new int[values.size()];
            for (int i = 0; i < values.size(); i++) {
                out[i] = values.get(i);
            }
            return out;
        }
    }
}
