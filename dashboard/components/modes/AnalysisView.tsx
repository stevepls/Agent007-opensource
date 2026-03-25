"use client";

import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Download,
  Table,
} from "lucide-react";
import type { TypedEntity } from "@/lib/viewProtocol";

interface AnalysisViewProps {
  entity: TypedEntity;   // type: "table" | "time_entries" | "metrics"
  onBack?: () => void;
}

export function AnalysisView({ entity, onBack }: AnalysisViewProps) {
  const d = entity.data;

  // Extract table data from entity
  const title = d.title || "Analysis";
  const columns: { key: string; label: string }[] = d.columns || [];
  const rows: Record<string, any>[] = d.rows || [];

  // If no columns defined, auto-detect from first row
  const effectiveColumns = useMemo(() => {
    if (columns.length > 0) return columns;
    if (rows.length === 0) return [];
    return Object.keys(rows[0]).map((key) => ({
      key,
      label: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    }));
  }, [columns, rows]);

  // Sorting
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    return [...rows].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") {
        return sortDir === "asc" ? va - vb : vb - va;
      }
      const sa = String(va).toLowerCase();
      const sb = String(vb).toLowerCase();
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
  }, [rows, sortKey, sortDir]);

  const toggleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  // Summary metrics (if provided)
  const metrics: { label: string; value: string | number }[] = d.metrics || [];

  return (
    <div className="flex flex-col h-full bg-[#0a0a0a]">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[#1a1a1a]">
        {onBack && (
          <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground" onClick={onBack}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
        )}
        <Table className="w-4 h-4 text-indigo-400" />
        <span className="text-sm font-semibold text-foreground">{title}</span>
        <Badge variant="outline" className="text-[11px] py-0 px-1.5 border-[#262626] text-muted-foreground">
          {rows.length} rows
        </Badge>
      </div>

      {/* Metrics summary (if provided) */}
      {metrics.length > 0 && (
        <div className="flex items-center gap-4 px-4 py-3 border-b border-[#1a1a1a]">
          {metrics.map((m, i) => (
            <div key={i} className="text-center">
              <p className="text-lg font-semibold text-foreground">{m.value}</p>
              <p className="text-[11px] text-muted-foreground">{m.label}</p>
            </div>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {effectiveColumns.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
            No data to display
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-[#0f0f0f] z-10">
              <tr>
                {effectiveColumns.map((col) => (
                  <th
                    key={col.key}
                    className="text-left text-xs font-medium text-muted-foreground px-4 py-2.5 border-b border-[#1a1a1a] cursor-pointer select-none hover:text-foreground transition-colors"
                    onClick={() => toggleSort(col.key)}
                  >
                    <span className="flex items-center gap-1">
                      {col.label}
                      {sortKey === col.key ? (
                        sortDir === "asc" ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />
                      ) : (
                        <ArrowUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-[#141414] hover:bg-[#141414] transition-colors"
                >
                  {effectiveColumns.map((col) => (
                    <td key={col.key} className="px-4 py-2.5 text-foreground">
                      {formatCell(row[col.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function formatCell(value: any): string {
  if (value == null) return "\u2014";
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
