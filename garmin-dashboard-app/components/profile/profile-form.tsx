"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Camera, Loader2 } from "lucide-react";
import type { Profile } from "@/lib/profile";

/** Downscales to a max dimension before base64-encoding, so a phone photo
 * doesn't turn into a multi-megabyte JSON file on disk. */
function resizeToDataUrl(file: File, maxDim = 480): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => {
      img.onerror = reject;
      img.onload = () => {
        const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
        const canvas = document.createElement("canvas");
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;
        const ctx = canvas.getContext("2d")!;
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  });
}

const fieldClass =
  "w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground outline-none focus:border-foreground/30";

export function ProfileForm({ initial }: { initial: Profile }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [photo, setPhoto] = useState(initial.photoDataUrl);
  const [name, setName] = useState(initial.name);
  const [aim, setAim] = useState(initial.aim);
  const [motivation, setMotivation] = useState(initial.motivation);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  async function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhoto(await resizeToDataUrl(file));
  }

  async function handleSave() {
    setSaving(true);
    try {
      await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, photoDataUrl: photo, aim, motivation }),
      });
      setSavedAt(Date.now());
      router.refresh();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="group relative h-24 w-24 shrink-0 overflow-hidden rounded-full border border-border bg-muted"
        >
          {photo ? (
            // eslint-disable-next-line @next/next/no-img-element -- local data: URL, not a remote asset
            <img src={photo} alt="" className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground">
              <Camera size={24} />
            </div>
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-foreground/0 text-transparent transition-colors group-hover:bg-foreground/40 group-hover:text-background">
            <Camera size={20} />
          </div>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handlePhotoChange}
        />
        <div className="flex-1">
          <label className="mb-1 block text-[11px] uppercase tracking-wider text-muted-foreground">
            Name
          </label>
          <input
            className={fieldClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-[11px] uppercase tracking-wider text-muted-foreground">
          Aim
        </label>
        <textarea
          className={fieldClass + " min-h-20 resize-y"}
          value={aim}
          onChange={(e) => setAim(e.target.value)}
          placeholder="What are you working toward? e.g. Run a 5k under 25 minutes"
        />
      </div>

      <div>
        <label className="mb-1 block text-[11px] uppercase tracking-wider text-muted-foreground">
          Motivation
        </label>
        <textarea
          className={fieldClass + " min-h-20 resize-y"}
          value={motivation}
          onChange={(e) => setMotivation(e.target.value)}
          placeholder="Why does this matter to you?"
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-full bg-foreground px-5 py-2 text-sm font-medium text-background disabled:opacity-60"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          Save
        </button>
        {savedAt && !saving && (
          <span className="text-xs text-muted-foreground">Saved</span>
        )}
      </div>
    </div>
  );
}
