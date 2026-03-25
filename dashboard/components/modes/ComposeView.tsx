"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  Send,
  X,
  Eye,
  Edit3,
  Loader2,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface ComposeViewProps {
  entity: TypedEntity;   // type: "email_draft"
  chatSlot?: React.ReactNode;  // For refinement chat
  onSend?: (data: { to: string; subject: string; body: string; html?: string }) => void;
  onDiscard?: () => void;
  onBack?: () => void;
}

export function ComposeView({ entity, chatSlot, onSend, onDiscard, onBack }: ComposeViewProps) {
  const d = entity.data;

  const [to, setTo] = useState(d.to || d.recipient || "");
  const [subject, setSubject] = useState(d.subject || "");
  const [body, setBody] = useState(d.body || d.content || "");
  const [htmlPreview, setHtmlPreview] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);

  // Try to render HTML preview from template
  useEffect(() => {
    if (d.template) {
      setLoading(true);
      fetch("/api/emails/render", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ template: d.template, props: d.template_props || {} }),
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.html) {
            setHtmlPreview(data.html);
            setPreviewMode(true);
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [d.template, d.template_props]);

  const handleSend = async () => {
    setSending(true);
    try {
      onSend?.({ to, subject, body, html: htmlPreview || undefined });
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1a1a1a]">
        {onBack && (
          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onBack}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
        )}
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Compose
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs gap-1.5 text-muted-foreground"
            onClick={() => setPreviewMode(!previewMode)}
          >
            {previewMode ? <Edit3 className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {previewMode ? "Edit" : "Preview"}
          </Button>
        </div>
      </div>

      {/* Fields + Editor */}
      <div className="flex-1 overflow-y-auto">
        {/* To / Subject fields */}
        <div className="px-4 py-3 space-y-2 border-b border-[#1a1a1a]">
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground w-16 flex-shrink-0">To</label>
            <input
              type="email"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="flex-1 text-sm bg-transparent border-none outline-none text-foreground placeholder:text-[#525252]"
              placeholder="recipient@example.com"
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted-foreground w-16 flex-shrink-0">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="flex-1 text-sm bg-transparent border-none outline-none text-foreground placeholder:text-[#525252]"
              placeholder="Subject line"
            />
          </div>
        </div>

        {/* Body */}
        <div className="px-4 py-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : previewMode && htmlPreview ? (
            /* HTML preview */
            <div
              className="bg-white rounded-lg p-4 max-w-xl mx-auto"
              dangerouslySetInnerHTML={{ __html: htmlPreview }}
            />
          ) : (
            /* Plain text editor */
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full min-h-[300px] text-sm bg-transparent border border-[#1a1a1a] rounded-lg p-3 outline-none text-foreground placeholder:text-[#525252] resize-y focus:border-indigo-500/50"
              placeholder="Write your message..."
            />
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-[#1a1a1a]">
        <Button
          size="sm"
          className="h-8 text-xs gap-1.5 bg-indigo-600 hover:bg-indigo-500 text-white"
          onClick={handleSend}
          disabled={sending || !to || !subject}
        >
          {sending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
          Send
        </Button>
        {onDiscard && (
          <Button variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground" onClick={onDiscard}>
            <X className="w-3.5 h-3.5 mr-1" />
            Discard
          </Button>
        )}
      </div>
    </div>
  );
}
