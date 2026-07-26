import { cn } from "@/lib/utils"

export function SabioMark({ className }: { className?: string }) {
  return (
    <img
      src="/favicon.svg"
      alt="Sabio"
      className={cn("size-8", className)}
    />
  )
}
