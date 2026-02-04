import { NextRequest } from "next/server";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY || "";

export async function POST(request: NextRequest) {
  console.log("[Transcribe] API called");
  console.log("[Transcribe] API key present:", !!OPENAI_API_KEY);
  console.log("[Transcribe] API key starts with:", OPENAI_API_KEY.slice(0, 8));

  if (!OPENAI_API_KEY) {
    console.error("[Transcribe] No API key configured");
    return new Response(
      JSON.stringify({ error: "OpenAI API key not configured" }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }

  try {
    const formData = await request.formData();
    const audioFile = formData.get("audio");

    console.log("[Transcribe] Audio file received:", !!audioFile);
    console.log("[Transcribe] Audio file type:", audioFile instanceof Blob ? "Blob" : typeof audioFile);

    if (!audioFile || !(audioFile instanceof Blob)) {
      console.error("[Transcribe] No valid audio file");
      return new Response(
        JSON.stringify({ error: "No audio file provided" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    console.log("[Transcribe] Audio size:", audioFile.size, "bytes");
    console.log("[Transcribe] Sending to OpenAI Whisper...");

    const whisperFormData = new FormData();
    whisperFormData.append("file", audioFile, "audio.webm");
    whisperFormData.append("model", "whisper-1");
    whisperFormData.append("language", "en");

    const response = await fetch("https://api.openai.com/v1/audio/transcriptions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${OPENAI_API_KEY}`,
      },
      body: whisperFormData,
    });

    console.log("[Transcribe] Whisper response status:", response.status);

    if (!response.ok) {
      const error = await response.text();
      console.error("[Transcribe] Whisper API error:", error);
      return new Response(
        JSON.stringify({ error: "Transcription failed", details: error }),
        { status: response.status, headers: { "Content-Type": "application/json" } }
      );
    }

    const result = await response.json();
    console.log("[Transcribe] Transcription successful, text length:", result.text?.length || 0);
    
    return new Response(
      JSON.stringify({ text: result.text }),
      { headers: { "Content-Type": "application/json" } }
    );
  } catch (error: any) {
    console.error("[Transcribe] Error:", error.message);
    return new Response(
      JSON.stringify({ error: "Internal server error", details: error.message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
}
