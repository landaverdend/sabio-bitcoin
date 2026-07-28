import { Code2, MessageCircle } from "lucide-react"

import { SabioMark } from "@/components/sabio-mark"
import { useLocale } from "@/lib/i18n"

export default function AboutPage() {
  const { t } = useLocale()

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <div className="flex shrink-0 items-center gap-3 border-b px-6 py-4">
        <SabioMark className="size-10 shrink-0" />
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">{t("aboutTitle")}</h1>
          <p className="truncate text-sm text-muted-foreground">{t("aboutTagline")}</p>
        </div>
      </div>

      <div className="flex-1 px-6 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-8">
          <p className="text-sm leading-relaxed text-muted-foreground">{t("aboutIntro")}</p>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-semibold">{t("aboutHowItWorksTitle")}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t("aboutHowItWorksIntro")}
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border p-4">
                <div className="mb-1.5 flex items-center gap-2">
                  <Code2 className="size-4 shrink-0 text-sabio" />
                  <h3 className="text-sm font-medium">{t("aboutRepoAgentTitle")}</h3>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t("aboutRepoAgentDescription")}
                </p>
              </div>
              <div className="rounded-xl border p-4">
                <div className="mb-1.5 flex items-center gap-2">
                  <MessageCircle className="size-4 shrink-0 text-sabio" />
                  <h3 className="text-sm font-medium">{t("aboutCommsAgentTitle")}</h3>
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {t("aboutCommsAgentDescription")}
                </p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-semibold">{t("aboutEvidenceTitle")}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t("aboutEvidenceDescription")}
            </p>
          </section>

          <section className="flex flex-col gap-2">
            <h2 className="text-sm font-semibold">{t("aboutAccountTitle")}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              {t("aboutAccountDescription")}
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
