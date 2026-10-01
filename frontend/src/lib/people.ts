import type { MemberStatus, UserRole } from "@/lib/types";

/** As People shows them (backend app/api/routes/people.py). */
export const ROLE_LABELS: Record<UserRole, string> = { admin: "Admin", auditor: "Auditor", viewer: "Viewer" };
export const ROLES: UserRole[] = ["admin", "auditor", "viewer"];

export const STATUS_LABELS: Record<MemberStatus, string> = {
  active: "Active",
  locked: "Locked",
  must_change_password: "Must change password",
  deactivated: "Deactivated",
};

/** How a person is named on screen: their name, else their email. */
export function displayName(person: { name: string | null; email: string }): string {
  return person.name || person.email;
}
