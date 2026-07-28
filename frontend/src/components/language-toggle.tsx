import { Languages } from "lucide-react"

import { SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar"
import { useLocale } from "@/lib/i18n"
import { cn } from "@/lib/utils"

export function LanguageToggle() {
  const { locale, setLocale, t } = useLocale()
  const spanishEnabled = locale === "es"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          type="button"
          role="switch"
          aria-checked={spanishEnabled}
          aria-label={t("useSpanish")}
          tooltip={spanishEnabled ? t("switchToEnglish") : t("switchToSpanish")}
          onClick={() => setLocale(spanishEnabled ? "en" : "es")}
        >
          <Languages />
          <span>Español</span>
          <div
            aria-hidden="true"
            className={cn(
              "ml-auto flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors",
              spanishEnabled ? "bg-sidebar-primary" : "bg-sidebar-border",
            )}
          >
            <span
              className={cn(
                "size-4 rounded-full bg-sidebar transition-transform",
                spanishEnabled && "translate-x-4",
              )}
            />
          </div>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
