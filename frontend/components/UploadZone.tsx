"use client";

import { useCallback, useRef, useState } from "react";
import { CheckCircle2, FileText, Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  label: string;
  description: string;
  file: File | null;
  onChange: (file: File) => void;
  disabled?: boolean;
}

export function UploadZone({
  label,
  description,
  file,
  onChange,
  disabled = false,
}: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;
      const dropped = e.dataTransfer.files[0];
      if (dropped) onChange(dropped);
    },
    [disabled, onChange]
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!disabled) setIsDragging(true);
  }, [disabled]);

  const handleDragLeave = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      // Only clear dragging if leaving the zone itself, not a child
      if (!e.currentTarget.contains(e.relatedTarget as Node)) {
        setIsDragging(false);
      }
    },
    []
  );

  const handleClick = () => {
    if (!disabled) inputRef.current?.click();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (picked) onChange(picked);
    // Reset so re-selecting the same file fires onChange again
    e.target.value = "";
  };

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`Upload ${label}`}
      onClick={handleClick}
      onKeyDown={(e) => e.key === "Enter" && handleClick()}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className={cn(
        "relative flex min-h-[130px] flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-all duration-150",
        !disabled && "cursor-pointer",
        disabled && "cursor-not-allowed opacity-50",
        isDragging
          ? "border-primary/60 bg-primary/5 scale-[1.01]"
          : file
          ? "border-emerald-400/60 bg-emerald-50/60 dark:bg-emerald-950/20"
          : "border-border hover:border-muted-foreground/40 hover:bg-muted/30"
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        onChange={handleInputChange}
        disabled={disabled}
        tabIndex={-1}
      />

      {file ? (
        <>
          <CheckCircle2 className="h-7 w-7 shrink-0 text-emerald-500" />
          <div className="space-y-0.5">
            <p className="text-sm font-medium leading-snug text-foreground">
              {file.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {(file.size / 1024).toFixed(1)} KB · Click to replace
            </p>
          </div>
        </>
      ) : (
        <>
          {isDragging ? (
            <FileText className="h-7 w-7 shrink-0 text-primary" />
          ) : (
            <Upload className="h-7 w-7 shrink-0 text-muted-foreground/70" />
          )}
          <div className="space-y-0.5">
            <p className="text-sm font-medium leading-snug text-foreground">
              {isDragging ? "Drop to upload" : label}
            </p>
            <p className="text-xs text-muted-foreground">{description}</p>
          </div>
        </>
      )}
    </div>
  );
}