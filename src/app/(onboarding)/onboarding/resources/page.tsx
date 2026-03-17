"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { setPendingFile, removePendingFile } from "@/stores/pending-files";
import { ProgressHeader } from "@/components/onboarding/progress-header";
import { Button } from "@/components/ui/button";
import { MaterialIcon } from "@/components/shared/material-icon";
import type { ResourceFileInfo } from "@/types/onboarding";

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50 MB
const MAX_FILES = 5;

const ACCEPTED_TYPES: Record<string, "pdf" | "pptx" | "docx"> = {
  "application/pdf": "pdf",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
};

const ACCEPT_STRING = Object.keys(ACCEPTED_TYPES).join(",") + ",.pdf,.pptx,.docx";

function getFileType(file: File): "pdf" | "pptx" | "docx" | null {
  const ext = file.name.split(".").pop()?.toLowerCase();
  if (file.type === "application/pdf" || ext === "pdf") return "pdf";
  if (
    file.type ===
      "application/vnd.openxmlformats-officedocument.presentationml.presentation" ||
    ext === "pptx"
  )
    return "pptx";
  if (
    file.type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    ext === "docx"
  )
    return "docx";
  return null;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getFileIcon(type: "pdf" | "pptx" | "docx"): string {
  switch (type) {
    case "pdf":
      return "picture_as_pdf";
    case "pptx":
      return "slideshow";
    case "docx":
      return "description";
  }
}

export default function ResourcesPage() {
  const router = useRouter();
  const { resources, setResources, setCurrentStep } = useOnboardingStore();

  const [files, setFiles] = useState<ResourceFileInfo[]>(resources.files);
  const [errors, setErrors] = useState<string[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFiles = useCallback(
    (incoming: FileList | File[]) => {
      const newErrors: string[] = [];
      const accepted: { info: ResourceFileInfo; file: File }[] = [];

      const incomingArray = Array.from(incoming);

      for (const file of incomingArray) {
        // Check total count
        if (files.length + accepted.length >= MAX_FILES) {
          newErrors.push(`Maximum ${MAX_FILES} files allowed. "${file.name}" was not added.`);
          continue;
        }

        // Check file type
        const fileType = getFileType(file);
        if (!fileType) {
          newErrors.push(
            `"${file.name}" is not a supported file type. Only PDF, PPTX, and DOCX files are accepted.`
          );
          continue;
        }

        // Check file size
        if (file.size > MAX_FILE_SIZE) {
          newErrors.push(
            `"${file.name}" exceeds the 50 MB limit (${formatFileSize(file.size)}).`
          );
          continue;
        }

        // Check for duplicate file names
        const isDuplicate =
          files.some((f) => f.fileName === file.name) ||
          accepted.some((a) => a.info.fileName === file.name);
        if (isDuplicate) {
          newErrors.push(`"${file.name}" has already been added.`);
          continue;
        }

        const id = crypto.randomUUID();
        accepted.push({
          info: {
            id,
            fileName: file.name,
            fileType,
            fileSizeBytes: file.size,
          },
          file,
        });
      }

      if (accepted.length > 0) {
        // Store File objects in the pending-files module store
        for (const { info, file } of accepted) {
          setPendingFile(info.id, file);
        }
        setFiles((prev) => [...prev, ...accepted.map((a) => a.info)]);
      }

      setErrors(newErrors);
    },
    [files]
  );

  function handleRemoveFile(id: string) {
    setFiles((prev) => prev.filter((f) => f.id !== id));
    removePendingFile(id);
    setErrors([]);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  }

  function handleFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
    }
    // Reset the input so the same file can be re-selected
    e.target.value = "";
  }

  function handleContinue() {
    setResources({ files });
    setCurrentStep(6);
    router.push("/onboarding/review");
  }

  function handleSkip() {
    setResources({ files: [] });
    setCurrentStep(6);
    router.push("/onboarding/review");
  }

  function handleBack() {
    // Save current progress before going back
    if (files.length > 0) {
      setResources({ files });
    }
    router.push("/onboarding/assessment");
  }

  const canAddMore = files.length < MAX_FILES;

  return (
    <>
      <ProgressHeader currentStep={5} />

      <div className="text-center space-y-4">
        <h1 className="text-slate-900 dark:text-slate-100 text-4xl md:text-5xl font-bold tracking-tight leading-tight">
          Study Materials
        </h1>
        <p className="text-slate-500 dark:text-slate-400 text-lg">
          Upload your textbooks, teacher notes, or question papers (optional)
        </p>
      </div>

      {/* Drag & Drop Zone */}
      {canAddMore && (
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`w-full rounded-xl border-2 border-dashed p-10 transition-all cursor-pointer text-center ${
            isDragOver
              ? "border-primary bg-primary/5 scale-[1.01]"
              : "border-primary/20 bg-white dark:bg-slate-900 hover:border-primary/40 hover:bg-primary/[0.02]"
          }`}
        >
          <div className="flex flex-col items-center gap-3">
            <div
              className={`size-14 rounded-full flex items-center justify-center transition-colors ${
                isDragOver ? "bg-primary/10" : "bg-primary/5"
              }`}
            >
              <MaterialIcon
                name="upload_file"
                className={`text-3xl ${isDragOver ? "text-primary" : "text-primary/60"}`}
              />
            </div>
            <div>
              <p className="font-bold text-slate-900 dark:text-slate-100">
                {isDragOver ? "Drop files here" : "Drag & drop files here"}
              </p>
              <p className="text-sm text-slate-400 mt-1">
                or click to browse
              </p>
            </div>
            <p className="text-xs text-slate-400">
              PDF, PPTX, DOCX &middot; Max 50 MB per file &middot; Up to {MAX_FILES} files
            </p>
          </div>
        </button>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPT_STRING}
        multiple
        onChange={handleFileInputChange}
        className="hidden"
      />

      {/* Error Messages */}
      {errors.length > 0 && (
        <div className="space-y-2">
          {errors.map((err, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-sm text-destructive bg-destructive/10 p-3 rounded-lg"
            >
              <MaterialIcon name="error" className="text-lg shrink-0 mt-0.5" />
              <span>{err}</span>
            </div>
          ))}
        </div>
      )}

      {/* File List */}
      {files.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-bold text-slate-500">
            {files.length} {files.length === 1 ? "file" : "files"} added
          </p>
          {files.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-4 p-4 rounded-xl border border-primary/10 bg-white dark:bg-slate-900"
            >
              <div className="size-10 rounded-lg bg-primary/5 flex items-center justify-center shrink-0">
                <MaterialIcon
                  name={getFileIcon(f.fileType)}
                  className="text-xl text-primary"
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm text-slate-900 dark:text-slate-100 truncate">
                  {f.fileName}
                </p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {f.fileType.toUpperCase()} &middot; {formatFileSize(f.fileSizeBytes)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleRemoveFile(f.id)}
                className="size-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-destructive hover:bg-destructive/10 transition-all shrink-0"
                aria-label={`Remove ${f.fileName}`}
              >
                <MaterialIcon name="close" className="text-lg" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex flex-col gap-4 pt-6 border-t border-primary/5">
        {files.length > 0 ? (
          <Button
            onClick={handleContinue}
            size="lg"
            className="w-full text-lg shadow-lg shadow-primary/20"
          >
            Continue
            <MaterialIcon name="arrow_forward" className="text-xl" />
          </Button>
        ) : (
          <Button
            onClick={handleSkip}
            size="lg"
            className="w-full text-lg shadow-lg shadow-primary/20"
          >
            Skip &mdash; I&apos;ll add materials later
            <MaterialIcon name="arrow_forward" className="text-xl" />
          </Button>
        )}

        {files.length > 0 && (
          <button
            onClick={handleSkip}
            className="w-full py-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
          >
            Skip without materials
          </button>
        )}

        <button
          onClick={handleBack}
          className="w-full py-3 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors text-sm font-medium"
        >
          Back
        </button>
      </div>
    </>
  );
}
