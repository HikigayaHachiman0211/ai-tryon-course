/**
 * Audio encoding utilities — converts browser MediaRecorder output (typically webm/opus)
 * to 16-bit PCM WAV format compatible with MiMo ASR.
 *
 * Uses Web Audio API (AudioContext.decodeAudioData) to decode any browser-native format,
 * then re-encodes as linear PCM WAV.
 */

/**
 * Convert an audio Blob (any browser-supported format) to a WAV Blob.
 *
 * Steps:
 * 1. Read blob as ArrayBuffer
 * 2. Decode via AudioContext.decodeAudioData (handles webm, ogg, mp4, etc.)
 * 3. Encode decoded PCM as 16-bit WAV
 *
 * Returns a Blob with type 'audio/wav'.
 * Throws if the browser cannot decode the input format.
 */
export async function convertToWav(inputBlob: Blob): Promise<Blob> {
  const arrayBuffer = await inputBlob.arrayBuffer();

  // Use OfflineAudioContext for decode (no audio output)
  const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();

  let audioBuffer: AudioBuffer;
  try {
    audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
  } catch {
    await audioCtx.close();
    throw new Error('DECODE_FAILED');
  } finally {
    // AudioContext.decodeAudioData detaches the ArrayBuffer, so we can't reuse it
  }

  // Encode to WAV
  const wavBlob = encodeAudioBufferToWav(audioBuffer);
  await audioCtx.close();
  return wavBlob;
}

/**
 * Encode an AudioBuffer to a 16-bit PCM WAV Blob.
 */
function encodeAudioBufferToWav(buffer: AudioBuffer): Blob {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitsPerSample = 16;

  // Interleave channels
  const channels: Float32Array[] = [];
  for (let ch = 0; ch < numChannels; ch++) {
    channels.push(buffer.getChannelData(ch));
  }

  const numFrames = buffer.length;
  const bytesPerSample = bitsPerSample / 8;
  const blockAlign = numChannels * bytesPerSample;
  const dataSize = numFrames * blockAlign;
  const headerSize = 44;
  const totalSize = headerSize + dataSize;

  const arrayBuffer = new ArrayBuffer(totalSize);
  const view = new DataView(arrayBuffer);

  // WAV header
  writeString(view, 0, 'RIFF');
  view.setUint32(4, totalSize - 8, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  // Write interleaved PCM samples
  let offset = 44;
  for (let i = 0; i < numFrames; i++) {
    for (let ch = 0; ch < numChannels; ch++) {
      const sample = channels[ch][i];
      // Clamp to [-1, 1] and convert to 16-bit signed integer
      const clamped = Math.max(-1, Math.min(1, sample));
      const int16 = clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF;
      view.setInt16(offset, int16, true);
      offset += 2;
    }
  }

  return new Blob([arrayBuffer], { type: 'audio/wav' });
}

function writeString(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

/**
 * Check if a Blob is already WAV format (by MIME type).
 */
export function isWavBlob(blob: Blob): boolean {
  const t = blob.type.toLowerCase();
  return t === 'audio/wav' || t === 'audio/wave' || t === 'audio/x-wav';
}

/**
 * Get the appropriate file extension and format field for a blob.
 * Returns null format for unsupported types — caller must check and reject.
 */
export function getAudioFileInfo(blob: Blob): { ext: string; format: 'wav' | 'mp3' | null } {
  if (isWavBlob(blob)) return { ext: 'wav', format: 'wav' };
  if (blob.type.includes('mpeg') || blob.type.includes('mp3')) return { ext: 'mp3', format: 'mp3' };
  // Unsupported — do NOT default to wav; caller must handle null
  return { ext: 'bin', format: null };
}
