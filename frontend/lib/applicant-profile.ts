import { z } from "zod";
import { useSyncExternalStore } from "react";

import type { FormValues } from "@/lib/types";

export const APPLICATION_PROFILE_STORAGE_KEY = "skyoffer.applicant_profile.v1";

export const INITIAL_VALUES: FormValues = {
  educationStatus: "undergraduate",
  graduationYear: "2027",
  institution: "",
  institutionRecognition: "unknown",
  major: "",
  degreeType: "工学学士",
  gradeValue: "",
  gradingScale: "100",
  courses: "",
  languageType: "",
  languageTotal: "",
  listening: "",
  reading: "",
  writing: "",
  speaking: "",
  workMonths: "",
  experienceTitle: "",
  experienceDescription: "",
  targetRegions: ["hong_kong", "united_kingdom"],
  targetDirections: ["computer_science", "artificial_intelligence"],
  careerGoal: "",
  portfolio: "",
  interview: "",
  recommendation: "",
};

const formValuesSchema = z.object({
  educationStatus: z.enum(["undergraduate", "graduated", "other"]),
  graduationYear: z.string(),
  institution: z.string(),
  institutionRecognition: z.enum(["unknown", "mainland_recognized", "mainland_priority"]),
  major: z.string(),
  degreeType: z.string(),
  gradeValue: z.string(),
  gradingScale: z.string(),
  courses: z.string(),
  languageType: z.enum(["", "IELTS", "TOEFL", "PTE"]),
  languageTotal: z.string(),
  listening: z.string(),
  reading: z.string(),
  writing: z.string(),
  speaking: z.string(),
  workMonths: z.string(),
  experienceTitle: z.string(),
  experienceDescription: z.string(),
  targetRegions: z.array(z.enum(["hong_kong", "united_kingdom"])),
  targetDirections: z.array(z.enum([
    "computer_science",
    "artificial_intelligence",
    "aerospace_engineering",
    "low_altitude_economy",
  ])),
  careerGoal: z.string(),
  portfolio: z.enum(["", "true", "false"]),
  interview: z.enum(["", "true", "false"]),
  recommendation: z.enum(["", "true", "false"]),
});

export const applicantProfileSchema = z.object({
  schema_version: z.literal("applicant_profile.v1"),
  saved_at: z.string().datetime(),
  values: formValuesSchema,
});

export type ApplicantProfile = z.infer<typeof applicantProfileSchema>;

const PROFILE_CHANGED_EVENT = "skyoffer:applicant-profile-changed";
let cachedRaw: string | null | undefined;
let cachedProfile: ApplicantProfile | null = null;

function browserStorage(): Storage | null {
  return typeof window === "undefined" ? null : window.localStorage;
}

export function loadApplicationProfile(storage: Storage | null = browserStorage()): ApplicantProfile | null {
  if (!storage) return null;
  const raw = storage.getItem(APPLICATION_PROFILE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = applicantProfileSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

function getProfileSnapshot(): ApplicantProfile | null {
  const storage = browserStorage();
  if (!storage) return null;
  const raw = storage.getItem(APPLICATION_PROFILE_STORAGE_KEY);
  if (raw === cachedRaw) return cachedProfile;
  cachedRaw = raw;
  cachedProfile = loadApplicationProfile(storage);
  return cachedProfile;
}

function subscribeToProfile(callback: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key && event.key !== APPLICATION_PROFILE_STORAGE_KEY) return;
    cachedRaw = undefined;
    callback();
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(PROFILE_CHANGED_EVENT, callback);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(PROFILE_CHANGED_EVENT, callback);
  };
}

export function useApplicationProfile(): ApplicantProfile | null {
  return useSyncExternalStore(subscribeToProfile, getProfileSnapshot, () => null);
}

export function saveApplicationProfile(
  values: FormValues,
  storage: Storage | null = browserStorage(),
  savedAt = new Date(),
): ApplicantProfile {
  if (!storage) throw new Error("当前浏览器不支持本地保存。");
  const profile = applicantProfileSchema.parse({
    schema_version: "applicant_profile.v1",
    saved_at: savedAt.toISOString(),
    values,
  });
  storage.setItem(APPLICATION_PROFILE_STORAGE_KEY, JSON.stringify(profile));
  if (storage === browserStorage()) {
    cachedRaw = JSON.stringify(profile);
    cachedProfile = profile;
    window.dispatchEvent(new Event(PROFILE_CHANGED_EVENT));
  }
  return profile;
}

export function clearApplicationProfile(storage: Storage | null = browserStorage()): void {
  storage?.removeItem(APPLICATION_PROFILE_STORAGE_KEY);
  if (storage && storage === browserStorage()) {
    cachedRaw = null;
    cachedProfile = null;
    window.dispatchEvent(new Event(PROFILE_CHANGED_EVENT));
  }
}
