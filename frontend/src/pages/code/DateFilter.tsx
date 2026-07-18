import { Calendar, ChevronLeft, ChevronRight } from "lucide-react"
import { useState } from "react"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]
// Bitcoin Core's first commit is 2009 -- a fixed range covers the whole repo
// history without needing to derive it from data just for a <select>.
const YEARS = Array.from({ length: new Date().getFullYear() - 2008 }, (_, i) => 2009 + i)

export type DateRange = { since: string; until: string }

function toDateKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}

function formatLabel(dateKey: string): string {
  const [y, m, d] = dateKey.split("-").map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function formatRangeLabel(range: DateRange): string {
  if (range.since === range.until) return formatLabel(range.since)
  return `${formatLabel(range.since)} – ${formatLabel(range.until)}`
}

type DateFilterProps = {
  selected: DateRange | null
  onSelect: (range: DateRange | null) => void
}

export function DateFilter({ selected, onSelect }: DateFilterProps) {
  const today = new Date()
  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(today.getFullYear())
  const [viewMonth, setViewMonth] = useState(today.getMonth())
  // Set on the first click of a new range, cleared once the second click
  // commits it -- lets the grid preview the in-progress range on hover
  // before the user has picked an end date.
  const [pendingFrom, setPendingFrom] = useState<string | null>(null)
  const [hoverKey, setHoverKey] = useState<string | null>(null)

  const changeMonth = (delta: number) => {
    const next = new Date(viewYear, viewMonth + delta, 1)
    setViewYear(next.getFullYear())
    setViewMonth(next.getMonth())
  }

  const firstOfMonth = new Date(viewYear, viewMonth, 1)
  const startOffset = firstOfMonth.getDay()
  const cells = Array.from({ length: 42 }, (_, i) => new Date(viewYear, viewMonth, i - startOffset + 1))

  const todayKey = toDateKey(today)

  const pickDay = (date: Date) => {
    const key = toDateKey(date)
    if (!pendingFrom) {
      setPendingFrom(key)
      return
    }
    const range: DateRange =
      key >= pendingFrom ? { since: pendingFrom, until: key } : { since: key, until: pendingFrom }
    onSelect(range)
    setPendingFrom(null)
    setHoverKey(null)
    setOpen(false)
  }

  const previewStart = pendingFrom ?? selected?.since ?? null
  const previewEndRaw = pendingFrom ? (hoverKey ?? pendingFrom) : (selected?.until ?? null)
  const rangeLo = previewStart && previewEndRaw ? (previewStart < previewEndRaw ? previewStart : previewEndRaw) : null
  const rangeHi = previewStart && previewEndRaw ? (previewStart < previewEndRaw ? previewEndRaw : previewStart) : null

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setPendingFrom(null)
          setHoverKey(null)
        }
      }}
    >
      <PopoverTrigger className="flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-sm text-muted-foreground hover:bg-accent hover:text-foreground">
        <Calendar className="size-3.5" />
        {selected ? formatRangeLabel(selected) : "All time"}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        {pendingFrom && (
          <p className="mb-2 text-xs text-muted-foreground">
            Since {formatLabel(pendingFrom)} — pick an end date
          </p>
        )}
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <select
              value={viewMonth}
              onChange={(e) => setViewMonth(Number(e.target.value))}
              className="rounded-md border bg-transparent px-1.5 py-1 text-sm outline-none"
            >
              {MONTHS.map((m, i) => (
                <option key={m} value={i}>
                  {m}
                </option>
              ))}
            </select>
            <select
              value={viewYear}
              onChange={(e) => setViewYear(Number(e.target.value))}
              className="rounded-md border bg-transparent px-1.5 py-1 text-sm outline-none"
            >
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => changeMonth(-1)}
              className="rounded-md border p-1 hover:bg-accent"
              aria-label="Previous month"
            >
              <ChevronLeft className="size-3.5" />
            </button>
            <button
              type="button"
              onClick={() => changeMonth(1)}
              className="rounded-md border p-1 hover:bg-accent"
              aria-label="Next month"
            >
              <ChevronRight className="size-3.5" />
            </button>
          </div>
        </div>

        <div
          className="grid grid-cols-7 gap-y-1 text-center text-xs"
          onMouseLeave={() => setHoverKey(null)}
        >
          {WEEKDAYS.map((d) => (
            <span key={d} className="py-1 font-medium text-muted-foreground">
              {d}
            </span>
          ))}
          {cells.map((date) => {
            const key = toDateKey(date)
            const inMonth = date.getMonth() === viewMonth
            const isToday = key === todayKey
            const isEndpoint = key === rangeLo || key === rangeHi
            const isInRange = !!rangeLo && !!rangeHi && key > rangeLo && key < rangeHi
            return (
              <button
                key={key}
                type="button"
                onClick={() => pickDay(date)}
                onMouseEnter={() => setHoverKey(key)}
                className={cn(
                  "rounded-md py-1.5 text-sm hover:bg-accent",
                  !inMonth && "text-muted-foreground/40",
                  isToday && !isEndpoint && "font-semibold text-primary underline underline-offset-4",
                  isInRange && "rounded-none bg-accent",
                  isEndpoint && "bg-primary text-primary-foreground hover:bg-primary/90",
                )}
              >
                {date.getDate()}
              </button>
            )
          })}
        </div>

        <div className="mt-3 flex items-center justify-between border-t pt-2 text-sm">
          <button
            type="button"
            onClick={() => {
              onSelect(null)
              setPendingFrom(null)
              setOpen(false)
            }}
            className="font-medium hover:underline"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => {
              setViewYear(today.getFullYear())
              setViewMonth(today.getMonth())
              setPendingFrom(null)
              onSelect({ since: todayKey, until: todayKey })
              setOpen(false)
            }}
            className="text-muted-foreground hover:underline"
          >
            Today
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
