import { Monitor, Moon, Sun } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { useLocale, type TranslationKey } from "@/lib/i18n"

const options = [
  { value: "light", labelKey: "themeLight", icon: Sun },
  { value: "dark", labelKey: "themeDark", icon: Moon },
  { value: "system", labelKey: "themeSystem", icon: Monitor },
] as const satisfies ReadonlyArray<{
  value: "light" | "dark" | "system"
  labelKey: TranslationKey
  icon: typeof Sun
}>

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const { t } = useLocale()
  const current = options.find((option) => option.value === theme) ?? options[2]

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger render={<SidebarMenuButton tooltip={t("theme")} />}>
            <current.icon />
            <span>{t(current.labelKey)}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start">
            {options.map((option) => (
              <DropdownMenuItem key={option.value} onClick={() => setTheme(option.value)}>
                <option.icon />
                <span>{t(option.labelKey)}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
