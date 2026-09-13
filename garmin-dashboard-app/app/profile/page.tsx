import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { getProfile } from "@/lib/profile";
import { ProfileForm } from "@/components/profile/profile-form";

export const dynamic = "force-dynamic";

export default async function ProfilePage() {
  const profile = await getProfile();

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-6 sm:max-w-xl lg:pt-10">
      <header className="flex flex-col gap-4">
        <Link
          href="/"
          className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft size={16} />
          Today&rsquo;s health
        </Link>
        <h1 className="font-display text-3xl font-medium text-foreground">
          Profile
        </h1>
      </header>

      <div className="rounded-2xl border border-border bg-card p-5">
        <ProfileForm initial={profile} />
      </div>
    </main>
  );
}
