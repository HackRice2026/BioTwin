import { getProfile, saveProfile, type Profile } from "@/lib/profile";

export async function GET() {
  return Response.json(await getProfile());
}

export async function PUT(request: Request) {
  const body = (await request.json()) as Partial<Profile>;
  const current = await getProfile();
  const next: Profile = {
    name: body.name ?? current.name,
    photoDataUrl: body.photoDataUrl !== undefined ? body.photoDataUrl : current.photoDataUrl,
    aim: body.aim ?? current.aim,
    motivation: body.motivation ?? current.motivation,
  };
  await saveProfile(next);
  return Response.json(next);
}
