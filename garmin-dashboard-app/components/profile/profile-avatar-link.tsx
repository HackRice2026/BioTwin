import Link from "next/link";
import { User } from "lucide-react";

export function ProfileAvatarLink({ photoDataUrl }: { photoDataUrl: string | null }) {
  return (
    <Link
      href="/profile"
      className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted text-muted-foreground hover:border-foreground/30"
      aria-label="Profile"
    >
      {photoDataUrl ? (
        // eslint-disable-next-line @next/next/no-img-element -- local data: URL, not a remote asset
        <img src={photoDataUrl} alt="" className="h-full w-full object-cover" />
      ) : (
        <User size={18} />
      )}
    </Link>
  );
}
