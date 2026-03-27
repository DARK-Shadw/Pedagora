declare module "@met4citizen/headtts" {
  export class HeadTTS {
    constructor(options?: Record<string, unknown>);
    onstart: (() => void) | null;
    onmessage: ((message: { type: string; data: Record<string, unknown> }) => void) | null;
    onend: (() => void) | null;
    onerror: ((error: unknown) => void) | null;
    connect(
      settings?: Record<string, unknown> | null,
      onprogress?: ((event: ProgressEvent) => void) | null,
      onerror?: ((error: unknown) => void) | null
    ): Promise<void>;
    setup(data: Record<string, unknown>): Promise<void>;
    synthesize(data: {
      input: string | Array<string | Record<string, unknown>>;
      userData?: unknown;
    }, onmessage?: ((message: unknown) => void) | null, onerror?: ((error: unknown) => void) | null): Promise<unknown[]>;
    custom(data: Record<string, unknown>): Promise<unknown>;
    clear(): void;
  }
}
