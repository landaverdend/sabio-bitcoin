import { useEffect, useState } from "react"

/** Delays following `value` until it's stayed the same for `delayMs` --
 * for feeding a search box's text into a query key. Without this, every
 * keystroke re-fires the query immediately (confirmed in production: a
 * few seconds of typing in the People search box logged a full round trip
 * per character -- "greg", then "greg+m", "greg+maxw", etc., each its own
 * request). The input itself should still update on every keystroke for
 * responsiveness; only the value handed to the query should lag. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
