import { useState } from "react";
import { X } from "lucide-react";
import { focusRing } from "@/lib/theme";

const SS_KEY = "vs.narrowBannerDismissed";

export function TooNarrowBanner({ isDark }: { isDark: boolean }) {
  const [dismissed, setDismissed] = useState<boolean>(
    () => sessionStorage.getItem(SS_KEY) === "true",
  );
  if (dismissed) return null;

  const wrap = isDark
    ? "bg-amber-900/30 border-amber-600/40 text-amber-100"
    : "bg-amber-50 border-amber-300 text-amber-800";

  return (
    <div className={`flex items-center justify-between gap-3 px-4 py-2 border-b text-sm ${wrap}`}>
      <span>Voice Studio is optimized for screens at least 1024px wide.</span>
      <button
        type="button"
        onClick={() => {
          sessionStorage.setItem(SS_KEY, "true");
          setDismissed(true);
        }}
        className={`p-1 rounded shrink-0 ${focusRing}`}
        title="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
