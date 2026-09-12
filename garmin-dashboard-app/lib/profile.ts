import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";

export type Profile = {
  name: string;
  photoDataUrl: string | null;
  aim: string;
  motivation: string;
};

const DEFAULT_PROFILE: Profile = {
  name: "",
  photoDataUrl: null,
  aim: "",
  motivation: "",
};

// Personal data (name/photo/goals) has nothing to do with the Garmin time
// series in InfluxDB, and there's exactly one user of this app -- a plain
// local JSON file is the honest amount of infrastructure for that, not a
// database. Gitignored (see .gitignore) since it holds a real name/photo.
const DATA_DIR = path.join(process.cwd(), "data");
const PROFILE_PATH = path.join(DATA_DIR, "profile.json");

export async function getProfile(): Promise<Profile> {
  try {
    const raw = await readFile(PROFILE_PATH, "utf-8");
    return { ...DEFAULT_PROFILE, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PROFILE;
  }
}

export async function saveProfile(profile: Profile): Promise<void> {
  await mkdir(DATA_DIR, { recursive: true });
  await writeFile(PROFILE_PATH, JSON.stringify(profile, null, 2), "utf-8");
}
