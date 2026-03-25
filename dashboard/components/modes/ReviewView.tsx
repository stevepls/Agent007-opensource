"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ExternalLink,
  GitPullRequest,
  Check,
  MessageSquare,
  XCircle,
  FileCode,
  Plus,
  Minus,
  ChevronDown,
  ChevronRight,
  User,
  GitBranch,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface ReviewViewProps {
  entity: TypedEntity;
  onBack?: () => void;
  onApprove?: () => void;
  onRequestChanges?: (comment: string) => void;
  onComment?: (comment: string) => void;
}

export function ReviewView({ entity, onBack, onApprove, onRequestChanges, onComment }: ReviewViewProps) {
  const d = entity.data;
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [commentText, setCommentText] = useState("");
  const [activeTab, setActiveTab] = useState<"files" | "diff">("files");

  const files: Array<{ name: string; additions: number; deletions: number; patch?: string }> = d.files || [];
  const diff: string = d.diff || "";

  const statusColorMap: Record<string, string> = {
    approved: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    changes_requested: "text-amber-400 bg-amber-500/10 border-amber-500/20",
    pending: "text-zinc-400 bg-zinc-500/10 border-zinc-500/20",
  };
  const reviewStatusColor = statusColorMap[d.review_status || "pending"] || statusColorMap.pending;

  const toggleFile = (name: string) => {
    setExpandedFiles(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1a1a1a]">
        <div className="flex items-center gap-3 mb-2">
          {onBack && (
            <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onBack}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
          )}
          <GitPullRequest className="w-4 h-4 text-purple-400" />
          <span className="text-sm font-semibold text-foreground flex-1 truncate">
            {d.title || "Pull Request"}
          </span>
          {d.url && (
            <a href={d.url} target="_blank" rel="noopener noreferrer"
               className="text-muted-foreground hover:text-indigo-400 transition-colors">
              <ExternalLink className="w-4 h-4" />
            </a>
          )}
        </div>

        {/* PR metadata */}
        <div className="flex items-center gap-3 flex-wrap text-xs">
          {d.number && (
            <span className="text-muted-foreground">#{d.number}</span>
          )}
          {d.author && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <User className="w-3 h-3" /> {d.author}
            </span>
          )}
          {d.branch && (
            <span className="flex items-center gap-1 text-muted-foreground">
              <GitBranch className="w-3 h-3" /> {d.branch}
            </span>
          )}
          <Badge variant="outline" className={cn("text-[11px] py-0 px-1.5", reviewStatusColor)}>
            {(d.review_status || "pending").replace(/_/g, " ")}
          </Badge>
          {d.additions != null && (
            <span className="flex items-center gap-0.5 text-emerald-400">
              <Plus className="w-3 h-3" />{d.additions}
            </span>
          )}
          {d.deletions != null && (
            <span className="flex items-center gap-0.5 text-red-400">
              <Minus className="w-3 h-3" />{d.deletions}
            </span>
          )}
          {d.changed_files != null && (
            <span className="text-muted-foreground">{d.changed_files} files</span>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-[#1a1a1a]">
        <button
          onClick={() => setActiveTab("files")}
          className={cn(
            "px-4 py-2 text-xs font-medium transition-colors",
            activeTab === "files" ? "text-indigo-400 border-b-2 border-indigo-400" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <FileCode className="w-3.5 h-3.5 inline mr-1.5" />
          Files ({files.length || d.changed_files || 0})
        </button>
        <button
          onClick={() => setActiveTab("diff")}
          className={cn(
            "px-4 py-2 text-xs font-medium transition-colors",
            activeTab === "diff" ? "text-indigo-400 border-b-2 border-indigo-400" : "text-muted-foreground hover:text-foreground"
          )}
        >
          Diff
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === "files" && (
          <div className="divide-y divide-[#141414]">
            {files.length > 0 ? files.map((file) => (
              <div key={file.name}>
                <button
                  onClick={() => toggleFile(file.name)}
                  className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-[#141414] transition-colors text-left"
                >
                  {expandedFiles.has(file.name) ?
                    <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> :
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                  }
                  <FileCode className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm text-foreground flex-1 truncate font-mono">{file.name}</span>
                  <span className="text-xs text-emerald-400">+{file.additions}</span>
                  <span className="text-xs text-red-400">-{file.deletions}</span>
                </button>
                {expandedFiles.has(file.name) && file.patch && (
                  <pre className="px-4 py-2 text-xs font-mono overflow-x-auto bg-[#0f0f0f] border-l-2 border-[#262626] mx-4 mb-2 rounded">
                    {file.patch.split("\n").map((line, i) => (
                      <div
                        key={i}
                        className={cn(
                          "px-2",
                          line.startsWith("+") && !line.startsWith("+++") && "bg-emerald-500/10 text-emerald-300",
                          line.startsWith("-") && !line.startsWith("---") && "bg-red-500/10 text-red-300",
                          line.startsWith("@@") && "text-indigo-400",
                        )}
                      >
                        {line}
                      </div>
                    ))}
                  </pre>
                )}
              </div>
            )) : (
              <div className="p-8 text-center text-muted-foreground text-sm">
                {diff ? "Switch to Diff tab to view changes" : "No file data available"}
              </div>
            )}
          </div>
        )}

        {activeTab === "diff" && (
          <pre className="p-4 text-xs font-mono overflow-x-auto">
            {diff ? diff.split("\n").map((line, i) => (
              <div
                key={i}
                className={cn(
                  "px-2",
                  line.startsWith("+") && !line.startsWith("+++") && "bg-emerald-500/10 text-emerald-300",
                  line.startsWith("-") && !line.startsWith("---") && "bg-red-500/10 text-red-300",
                  line.startsWith("@@") && "text-indigo-400",
                  line.startsWith("diff ") && "text-foreground font-semibold mt-3",
                )}
              >
                {line}
              </div>
            )) : (
              <div className="text-center text-muted-foreground py-8">No diff data available</div>
            )}
          </pre>
        )}

        {/* Description */}
        {d.description && (
          <div className="px-4 py-3 border-t border-[#1a1a1a]">
            <p className="text-xs text-muted-foreground mb-1 font-medium">Description</p>
            <p className="text-sm text-foreground whitespace-pre-wrap">{d.description}</p>
          </div>
        )}
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-t border-[#1a1a1a]">
        {onApprove && (
          <Button size="sm" className="h-8 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white" onClick={onApprove}>
            <Check className="w-3.5 h-3.5" />
            Approve
          </Button>
        )}
        {onRequestChanges && (
          <Button size="sm" variant="ghost" className="h-8 text-xs gap-1.5 text-amber-400 hover:text-amber-300"
            onClick={() => onRequestChanges(commentText || "Changes requested")}>
            <XCircle className="w-3.5 h-3.5" />
            Request Changes
          </Button>
        )}
        {onComment && (
          <div className="flex-1 flex items-center gap-2 ml-2">
            <input
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder="Add a comment..."
              className="flex-1 text-xs bg-[#141414] border border-[#262626] rounded px-2 py-1.5 text-foreground focus:border-indigo-500/50 outline-none"
              onKeyDown={(e) => {
                if (e.key === "Enter" && commentText.trim()) {
                  onComment(commentText);
                  setCommentText("");
                }
              }}
            />
            <Button variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
              onClick={() => { if (commentText.trim()) { onComment(commentText); setCommentText(""); } }}>
              <MessageSquare className="w-3.5 h-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
