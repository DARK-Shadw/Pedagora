import { cn } from "@/lib/utils";
import { MaterialIcon } from "./material-icon";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  className?: string;
}

const sizeMap = {
  sm: { icon: "size-6 text-xs", text: "text-lg" },
  md: { icon: "size-8 text-xl", text: "text-xl" },
  lg: { icon: "size-10 text-2xl", text: "text-2xl" },
};

export function Logo({ size = "md", showText = true, className }: LogoProps) {
  const s = sizeMap[size];

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className={cn(
          "bg-primary rounded-lg flex items-center justify-center text-white",
          s.icon
        )}
      >
        <MaterialIcon name="auto_awesome" />
      </div>
      {showText && (
        <h2
          className={cn(
            "text-slate-900 dark:text-white font-bold tracking-tight",
            s.text
          )}
        >
          Pedagora
        </h2>
      )}
    </div>
  );
}
