import { Skeleton } from "@/components/ui/skeleton"

type ListRowSkeletonProps = {
  avatar?: boolean
  lines?: 2 | 3
  trailing?: boolean
}

function ListRowSkeleton({ avatar, lines = 2, trailing }: ListRowSkeletonProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      {avatar && <Skeleton className="size-8 shrink-0 rounded-full" />}
      <div className="min-w-0 flex-1 space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-1/3" />
        {lines === 3 && <Skeleton className="h-3 w-4/5" />}
      </div>
      {trailing && <Skeleton className="h-4 w-16 shrink-0" />}
    </div>
  )
}

type ListSkeletonProps = ListRowSkeletonProps & {
  rows?: number
}

// Drop-in replacement for a "Loading…" string inside the same
// `overflow-hidden rounded-md border` row-list wrapper every list page
// already uses -- previews the real row shape instead of a blank gap while
// the first page (or a filter/tab-triggered refetch) is in flight.
export function ListSkeleton({ rows = 6, ...rowProps }: ListSkeletonProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={i > 0 ? "border-t" : ""}>
          <ListRowSkeleton {...rowProps} />
        </div>
      ))}
    </>
  )
}
