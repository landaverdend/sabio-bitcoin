import { cn } from "@/lib/utils"

// Same deterministic name -> color scheme as AuthorFilter's avatar, reused
// here so a person's placeholder color is consistent with their commits.
const AVATAR_COLORS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-amber-500",
  "bg-lime-500",
  "bg-emerald-500",
  "bg-teal-500",
  "bg-cyan-500",
  "bg-blue-500",
  "bg-indigo-500",
  "bg-violet-500",
  "bg-fuchsia-500",
  "bg-pink-500",
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

type PersonAvatarProps = {
  name: string
  size?: "sm" | "lg"
}

export function PersonAvatar({ name, size = "sm" }: PersonAvatarProps) {
  const color = AVATAR_COLORS[hashString(name) % AVATAR_COLORS.length]
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full font-semibold text-white",
        size === "sm" ? "size-8 text-sm" : "size-12 text-lg",
        color,
      )}
    >
      {name.trim().charAt(0).toUpperCase() || "?"}
    </span>
  )
}
