"use client";

import { BookOpen } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface NarrativeSummaryProps {
  narrative: string | null;
}

export function NarrativeSummary({ narrative }: NarrativeSummaryProps) {
  if (!narrative) return null;

  return (
    <Alert className="border-blue-200 bg-blue-50/60 dark:border-blue-800 dark:bg-blue-950/20">
      <BookOpen className="h-4 w-4 text-blue-600 dark:text-blue-400" />
      <AlertDescription className="text-sm leading-relaxed text-blue-900 dark:text-blue-200">
        {narrative}
      </AlertDescription>
    </Alert>
  );
}