import { useQuery } from "@tanstack/react-query";
import { api, jsonBody } from "../api/client";

export type ProfileFields = {
  display_name: string;
  avatar: string | null;
  work_role: string;
  specialties: string[];
  bio: string;
};

export type Profile = ProfileFields & { revision: number };

export const profileKey = (userId?: number) => ["auth", "profile", userId] as const;

export function useProfile(userId?: number) {
  return useQuery({
    queryKey: profileKey(userId),
    queryFn: ({ signal }) => api<Profile>("/api/auth/profile", { signal }),
    enabled: userId !== undefined,
    staleTime: 30_000,
  });
}

export function updateProfile(revision: number, fields: ProfileFields) {
  return api<Profile>("/api/auth/profile", {
    method: "PUT",
    revision,
    body: jsonBody(fields),
  });
}
