"use client";

import { useRef, useCallback, useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, Mic, MicOff, Paperclip, Loader2, X, FileText, Image as ImageIcon, File as FileIcon, AlertCircle } from "lucide-react";

export interface Attachment {
  id: string;
  name: string;
  type: string;
  size: number;
  data?: string;
  preview?: string;
}

interface ChatInputProps {
  input: string;
  handleInputChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  handleSubmit: (e: React.FormEvent<HTMLFormElement>, attachments?: Attachment[]) => void;
  isLoading: boolean;
  onAttachmentsChange?: (attachments: Attachment[]) => void;
}

function getBrowserInfo() {
  if (typeof window === "undefined") return { isFirefox: false, isChrome: false };
  const ua = navigator.userAgent.toLowerCase();
  return {
    isFirefox: ua.includes("firefox"),
    isChrome: ua.includes("chrome") && !ua.includes("edge"),
  };
}

export function ChatInput({ input, handleInputChange, handleSubmit, isLoading, onAttachmentsChange }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartTimeRef = useRef<number>(0);
  
  const [browserInfo, setBrowserInfo] = useState({ isFirefox: false, isChrome: false });
  const [isRecording, setIsRecording] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [isTranscribing, setIsTranscribing] = useState(false);

  useEffect(() => {
    setBrowserInfo(getBrowserInfo());
  }, []);

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const startRecording = useCallback(async () => {
    setVoiceError(null);
    audioChunksRef.current = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Try to use a supported format
      let mimeType = "audio/webm";
      if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        mimeType = "audio/webm;codecs=opus";
      } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
        mimeType = "audio/mp4";
      } else if (MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")) {
        mimeType = "audio/ogg;codecs=opus";
      }
      
      console.log("Using MIME type:", mimeType);
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const recordingDuration = Date.now() - recordingStartTimeRef.current;
        console.log("Recording duration:", recordingDuration, "ms");
        
        stream.getTracks().forEach(track => track.stop());
        
        if (audioChunksRef.current.length === 0) {
          setVoiceError("No audio recorded");
          return;
        }
        
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        console.log("Audio blob size:", audioBlob.size, "bytes");
        
        if (audioBlob.size === 0) {
          setVoiceError("Recording failed - no audio data");
          return;
        }
        
        if (recordingDuration < 500) {
          setVoiceError("Recording too short - please speak for at least 1 second");
          return;
        }
        
        await transcribeAudio(audioBlob, mimeType);
      };

      mediaRecorder.start();
      recordingStartTimeRef.current = Date.now();
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
    } catch (error: any) {
      console.error("Recording error:", error);
      setVoiceError(error.name === "NotAllowedError" 
        ? "Microphone access denied" 
        : "Microphone error: " + error.message);
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  const transcribeAudio = useCallback(async (audioBlob: Blob, mimeType: string) => {
    setIsTranscribing(true);
    try {
      const formData = new FormData();
      
      // Determine file extension from MIME type
      let extension = "webm";
      if (mimeType.includes("mp4")) extension = "mp4";
      else if (mimeType.includes("ogg")) extension = "ogg";
      else if (mimeType.includes("wav")) extension = "wav";
      
      formData.append("audio", audioBlob, `recording.${extension}`);

      console.log("Sending audio to /api/transcribe");
      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
      });

      const result = await response.json();
      
      if (!response.ok) {
        console.error("Transcription error:", result);
        throw new Error(result.error || "Transcription failed");
      }

      const { text } = result;
      console.log("Transcribed text:", text);
      
      if (!text || text.trim().length === 0) {
        setVoiceError("No speech detected in recording");
        return;
      }
      
      // Append transcribed text to input
      const newText = input ? input + " " + text : text;
      handleInputChange({ target: { value: newText } } as any);
    } catch (error: any) {
      console.error("Transcription error:", error);
      setVoiceError("Transcription failed: " + (error.message || "Unknown error"));
    } finally {
      setIsTranscribing(false);
    }
  }, [input, handleInputChange]);

  const handleVoiceClick = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;

    Promise.all(Array.from(files).map(file => new Promise<Attachment>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve({
        id: Math.random().toString(36).slice(2),
        name: file.name,
        type: file.type,
        size: file.size,
        data: reader.result as string,
        preview: file.type.startsWith("image/") ? reader.result as string : undefined,
      });
      reader.readAsDataURL(file);
    }))).then(newAtts => {
      const updated = [...attachments, ...newAtts];
      setAttachments(updated);
      onAttachmentsChange?.(updated);
    });
    e.target.value = "";
  }, [attachments, onAttachmentsChange]);

  const removeAttachment = useCallback((id: string) => {
    const updated = attachments.filter(a => a.id !== id);
    setAttachments(updated);
    onAttachmentsChange?.(updated);
  }, [attachments, onAttachmentsChange]);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    handleInputChange(e);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
  }, [handleInputChange]);

  const onSubmit = useCallback((e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (input.trim() || attachments.length) {
      handleSubmit(e, attachments);
      setAttachments([]);
      onAttachmentsChange?.([]);
    }
  }, [input, attachments, handleSubmit, onAttachmentsChange]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if ((input.trim() || attachments.length) && !isLoading) e.currentTarget.form?.requestSubmit();
    }
  }, [input, attachments, isLoading]);

  const getIcon = (type: string) => type.startsWith("image/") ? <ImageIcon className="w-4 h-4" /> : <FileIcon className="w-4 h-4" />;
  const formatSize = (b: number) => b < 1024 ? b + " B" : b < 1048576 ? (b/1024).toFixed(1) + " KB" : (b/1048576).toFixed(1) + " MB";

  return (
    <form onSubmit={onSubmit} className="p-4">
      <AnimatePresence>
        {voiceError && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="max-w-4xl mx-auto mb-3">
            <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5" />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-amber-400">{voiceError}</span>
                  <button type="button" onClick={() => setVoiceError(null)} className="p-1 hover:bg-amber-500/20 rounded"><X className="w-3 h-3 text-amber-400" /></button>
                </div>
                <p className="text-xs text-muted-foreground mt-1">Using OpenAI Whisper for transcription</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {attachments.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="max-w-4xl mx-auto mb-2">
            <div className="flex flex-wrap gap-2 p-2 bg-muted/30 rounded-lg">
              {attachments.map(att => (
                <motion.div key={att.id} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} className="flex items-center gap-2 px-3 py-1.5 bg-background rounded-md border border-border">
                  {att.preview ? <img src={att.preview} alt="" className="w-6 h-6 object-cover rounded" /> : getIcon(att.type)}
                  <span className="text-sm truncate max-w-[150px]">{att.name}</span>
                  <span className="text-xs text-muted-foreground">{formatSize(att.size)}</span>
                  <button type="button" onClick={() => removeAttachment(att.id)} className="p-0.5 hover:bg-muted rounded"><X className="w-3 h-3" /></button>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative flex items-end gap-2 max-w-4xl mx-auto">
        <div className="flex-1 relative">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={isTranscribing ? "⏳ Transcribing..." : isRecording ? "🎤 Recording... click to stop" : "Ask Agent007 anything..."}
            disabled={isLoading || isTranscribing}
            className={`min-h-[52px] max-h-[200px] pr-24 resize-none bg-muted/50 border-muted-foreground/20 focus:border-primary/50 rounded-xl ${isRecording ? "border-red-500 bg-red-500/5" : ""}`}
            rows={1}
          />
          <div className="absolute right-2 bottom-2 flex items-center gap-1">
            <label className="cursor-pointer">
              <input ref={fileInputRef} type="file" multiple accept="image/*,.pdf,.doc,.docx,.txt,.md,.json,.csv" onChange={handleFileChange} className="sr-only" />
              <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-muted pointer-events-none" disabled={isLoading} title="Attach files">
                <Paperclip className="w-4 h-4" />
              </Button>
            </label>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className={`h-8 w-8 ${isRecording ? "text-red-500 bg-red-500/20 animate-pulse" : isTranscribing ? "text-blue-500" : "text-muted-foreground hover:text-foreground hover:bg-muted"}`}
              disabled={isLoading || isTranscribing}
              onClick={handleVoiceClick}
              title={isTranscribing ? "Transcribing..." : isRecording ? "Stop recording" : "Voice input (Whisper AI)"}
            >
              {isTranscribing ? <Loader2 className="w-4 h-4 animate-spin" /> : isRecording ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </Button>
          </div>
        </div>
        <motion.div whileTap={{ scale: 0.95 }}>
          <Button type="submit" size="icon" className="h-[52px] w-[52px] rounded-xl bg-primary hover:bg-primary/90 shadow-lg shadow-primary/25" disabled={(!input.trim() && !attachments.length) || isLoading || isTranscribing}>
            {isLoading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </Button>
        </motion.div>
      </div>
      <p className="text-center text-xs text-muted-foreground mt-2">
        {isTranscribing ? (
          <span className="text-blue-400 flex items-center justify-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Transcribing with Whisper AI...
          </span>
        ) : isRecording ? (
          <span className="text-red-400 flex items-center justify-center gap-1">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            Recording... click mic to stop
          </span>
        ) : (
          <>Press <kbd className="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono">Enter</kbd> to send • Voice powered by Whisper AI</>
        )}
      </p>
    </form>
  );
}
