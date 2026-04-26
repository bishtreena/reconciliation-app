"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { UploadZone } from "@/components/UploadZone";
import { uploadCSVs, reconcileRun, getSampleData } from "@/lib/api";

type LoadingStep = "idle" | "uploading" | "reconciling";

const STEP_LABEL: Record<LoadingStep, string> = {
  idle: "",
  uploading: "Uploading files…",
  reconciling: "Running reconciliation pipeline…",
};

export default function UploadPage() {
  const router = useRouter();

  const [platformFile, setPlatformFile] = useState<File | null>(null);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [step, setStep] = useState<LoadingStep>("idle");
  const [error, setError] = useState<string | null>(null);

  const isLoading = step !== "idle";
  const canReconcile = platformFile !== null && bankFile !== null && !isLoading;

  // ── Helpers ────────────────────────────────────────────────────────────

  const runPipeline = async (platform: File, bank: File) => {
    setError(null);
    try {
      setStep("uploading");
      const { run_id } = await uploadCSVs(platform, bank);

      setStep("reconciling");
      await reconcileRun(run_id);

      router.push(`/dashboard/${run_id}`);
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.";
      setError(msg);
      setStep("idle");
    }
  };

  // ── Handlers ───────────────────────────────────────────────────────────

  const handleReconcile = () => {
    if (!platformFile || !bankFile) return;
    runPipeline(platformFile, bankFile);
  };

  const handleSampleData = async () => {
    setError(null);
    setStep("uploading");
    try {
      const { platform_csv, bank_csv } = await getSampleData();

      const toFile = (content: string, name: string) =>
        new File([new Blob([content], { type: "text/csv" })], name, {
          type: "text/csv",
        });

      const platformSample = toFile(
        platform_csv,
        "platform_transactions.csv"
      );
      const bankSample = toFile(bank_csv, "bank_settlements.csv");

      // Show the selected filenames before auto-submitting
      setPlatformFile(platformSample);
      setBankFile(bankSample);

      await runPipeline(platformSample, bankSample);
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to load sample data.";
      setError(msg);
      setStep("idle");
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-2xl px-4 py-16 sm:py-24">

        {/* Hero */}
        <div className="mb-10 text-center">
          <div className="mb-4 flex justify-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/60 px-3 py-1 text-xs font-medium text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5" />
              January 2026 · sample data included
            </span>
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl">
            Recon
          </h1>
          <p className="mt-2 text-lg font-medium text-foreground/70">
            Payments Reconciliation
          </p>
          <p className="mt-3 text-sm text-muted-foreground sm:text-base">
            Upload your platform export and bank settlement file to instantly
            surface timing gaps, rounding drift, duplicates, and orphan refunds.
          </p>
        </div>

        {/* Upload card */}
        <Card className="shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-base font-semibold">
              Upload CSV Files
            </CardTitle>
            <CardDescription className="text-sm">
              Both files must include the required columns. Drop them in below
              or use the January 2026 sample data to explore the dashboard.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-5">
            {/* Drop zones */}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Platform Transactions
                </p>
                <UploadZone
                  label="platform_transactions.csv"
                  description="Drag & drop or click to browse"
                  file={platformFile}
                  onChange={setPlatformFile}
                  disabled={isLoading}
                />
              </div>
              <div className="space-y-1.5">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Bank Settlements
                </p>
                <UploadZone
                  label="bank_settlements.csv"
                  description="Drag & drop or click to browse"
                  file={bankFile}
                  onChange={setBankFile}
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Progress indicator */}
            {isLoading && (
              <div className="flex items-center gap-2.5 rounded-md border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" />
                <span>{STEP_LABEL[step]}</span>
                <span className="ml-auto text-xs">This takes ~5 s</span>
              </div>
            )}

            {/* Error */}
            {error && !isLoading && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-2 pt-1 sm:flex-row">
              <Button
                className="flex-1 gap-2"
                disabled={!canReconcile}
                onClick={handleReconcile}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {step === "uploading" ? "Uploading…" : "Reconciling…"}
                  </>
                ) : (
                  "Reconcile"
                )}
              </Button>

              <Button
                variant="outline"
                className="flex-1"
                disabled={isLoading}
                onClick={handleSampleData}
              >
                Use sample data
              </Button>
            </div>

            {/* Column hint */}
            <p className="text-center text-xs text-muted-foreground">
              Platform needs:{" "}
              <span className="font-mono">
                txn_id, timestamp, amount, currency, customer_id, type,
                parent_txn_id, status
              </span>
            </p>
          </CardContent>
        </Card>

      </div>
    </main>
  );
}