"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Save,
  X,
  RefreshCw,
  Shield,
  Loader2,
  AlertTriangle,
  Check,
  Bot,
  Ticket,
  MessageSquare,
  Mail,
  Clock,
  GitBranch,
  Lock,
  CreditCard,
  Settings,
} from "lucide-react";

// Category icon mapping
const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  ai: <Bot className="w-4 h-4" />,
  ticketing: <Ticket className="w-4 h-4" />,
  communication: <MessageSquare className="w-4 h-4" />,
  email: <Mail className="w-4 h-4" />,
  time_tracking: <Clock className="w-4 h-4" />,
  devops: <GitBranch className="w-4 h-4" />,
  auth: <Lock className="w-4 h-4" />,
  accounting: <CreditCard className="w-4 h-4" />,
  other: <Settings className="w-4 h-4" />,
};

interface Credential {
  key: string;
  value_masked: string;
  is_set: boolean;
}

interface Category {
  label: string;
  credentials: Credential[];
}

interface CredentialsData {
  categories: Record<string, Category>;
  env_path: string;
  total_keys: number;
}

export function CredentialsManager() {
  const [data, setData] = useState<CredentialsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set());
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveResult, setSaveResult] = useState<{ key: string; success: boolean; message: string } | null>(null);

  const fetchCredentials = useCallback(async () => {
    try {
      const res = await fetch("/api/settings/credentials");
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch {
      // Silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCredentials();
  }, [fetchCredentials]);

  const toggleCategory = (catId: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(catId)) next.delete(catId);
      else next.add(catId);
      return next;
    });
  };

  const startEdit = (key: string) => {
    setEditingKey(key);
    setEditValue("");
    setSaveResult(null);
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditValue("");
  };

  const saveCredential = async () => {
    if (!editingKey) return;
    setSaving(true);
    try {
      const res = await fetch("/api/settings/credentials", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: editingKey, value: editValue }),
      });
      const result = await res.json();
      if (result.success) {
        setSaveResult({ key: editingKey, success: true, message: "Saved. Restart Orchestrator to apply." });
        setEditingKey(null);
        setEditValue("");
        fetchCredentials(); // Refresh
      } else {
        setSaveResult({ key: editingKey, success: false, message: result.error || "Save failed" });
      }
    } catch {
      setSaveResult({ key: editingKey!, success: false, message: "Network error" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <AlertTriangle className="w-6 h-6 mx-auto mb-2" />
        <p className="text-sm">Failed to load credentials</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-semibold text-foreground">Credentials</h2>
          <Badge variant="outline" className="text-[11px] py-0 px-1.5 border-[#262626] text-muted-foreground">
            {data.total_keys} keys
          </Badge>
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={fetchCredentials}>
          <RefreshCw className="w-3.5 h-3.5" />
        </Button>
      </div>

      {/* Save result toast */}
      <AnimatePresence>
        {saveResult && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-md text-xs",
              saveResult.success
                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                : "bg-red-500/10 text-red-400 border border-red-500/20"
            )}
          >
            {saveResult.success ? <Check className="w-3.5 h-3.5" /> : <AlertTriangle className="w-3.5 h-3.5" />}
            <span>{saveResult.message}</span>
            <button onClick={() => setSaveResult(null)} className="ml-auto">
              <X className="w-3 h-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Categories */}
      {Object.entries(data.categories).map(([catId, cat]) => {
        const isExpanded = expandedCats.has(catId);
        const setCount = cat.credentials.filter((c) => c.is_set).length;
        const totalCount = cat.credentials.length;
        const allSet = setCount === totalCount;

        return (
          <div key={catId}>
            {/* Category header */}
            <button
              onClick={() => toggleCategory(catId)}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-md hover:bg-[#1a1a1a] transition-colors group"
            >
              {isExpanded ? (
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
              )}
              <span className="text-muted-foreground">
                {CATEGORY_ICONS[catId] || <Settings className="w-4 h-4" />}
              </span>
              <span className="text-xs font-medium text-foreground">{cat.label}</span>
              <Badge
                variant="outline"
                className={cn(
                  "text-[10px] py-0 px-1.5 ml-auto",
                  allSet
                    ? "border-emerald-500/30 text-emerald-400"
                    : "border-amber-500/30 text-amber-400"
                )}
              >
                {setCount}/{totalCount}
              </Badge>
            </button>

            {/* Credentials list */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="pl-4 pr-2 pb-2 space-y-1">
                    {cat.credentials.map((cred) => {
                      const isEditing = editingKey === cred.key;

                      return (
                        <div
                          key={cred.key}
                          className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[#141414] transition-colors"
                        >
                          {/* Status dot */}
                          <span
                            className={cn(
                              "w-1.5 h-1.5 rounded-full flex-shrink-0",
                              cred.is_set ? "bg-emerald-400" : "bg-red-400"
                            )}
                          />

                          {/* Key name */}
                          <span className="text-[11px] font-mono text-muted-foreground flex-shrink-0 min-w-0">
                            {cred.key}
                          </span>

                          {isEditing ? (
                            /* Edit mode */
                            <div className="flex items-center gap-1 flex-1 min-w-0 ml-auto">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                placeholder="Enter new value"
                                className="flex-1 text-[11px] px-2 py-1 rounded bg-[#0a0a0a] border border-[#333] text-foreground font-mono focus:border-indigo-500 focus:outline-none min-w-0"
                                autoFocus
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveCredential();
                                  if (e.key === "Escape") cancelEdit();
                                }}
                              />
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-emerald-400 hover:text-emerald-300"
                                onClick={saveCredential}
                                disabled={saving}
                              >
                                {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 text-muted-foreground"
                                onClick={cancelEdit}
                              >
                                <X className="w-3 h-3" />
                              </Button>
                            </div>
                          ) : (
                            /* Display mode */
                            <>
                              <span className="text-[11px] font-mono text-[#525252] truncate flex-1 min-w-0 ml-2">
                                {cred.is_set ? cred.value_masked : "not set"}
                              </span>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-5 w-5 text-muted-foreground hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                                onClick={() => startEdit(cred.key)}
                                title={`Edit ${cred.key}`}
                              >
                                <Settings className="w-3 h-3" />
                              </Button>
                            </>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}

      {/* Footer */}
      <p className="text-[11px] text-[#525252] px-3">
        Source: {data.env_path}
      </p>
    </div>
  );
}
