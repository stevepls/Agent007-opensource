"use client";

import type { StructuredData } from "@/lib/utils";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function StructuredDataBlock({ data }: { data: StructuredData }) {
  return (
    <Card className="my-3 overflow-hidden border-primary/20">
      <div className="px-4 py-2 bg-accent/30 flex items-center justify-between">
        <span className="text-sm font-medium">{data.title}</span>
        <Badge variant="outline" className="text-xs">
          {data.total} {data.total === 1 ? "item" : "items"}
        </Badge>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            {data.columns.map((col) => (
              <TableHead key={col.key}>{col.label}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.rows.map((row, i) => (
            <TableRow key={i}>
              {data.columns.map((col) => (
                <TableCell key={col.key} className="max-w-[300px] truncate">
                  {row[col.key] || "\u2014"}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {data.total > data.rows.length && (
        <div className="px-4 py-2 text-xs text-muted-foreground bg-accent/10">
          Showing {data.rows.length} of {data.total}
        </div>
      )}
    </Card>
  );
}
