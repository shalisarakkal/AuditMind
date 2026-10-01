/** Where someone who must change their password is sent (a temporary or
 * expired one): every other page is refused until they do. */
export const CHANGE_PASSWORD_PATH = "/change-password";

/** The signed-in user's own page: their name, email, orgs and roles. */
export const ACCOUNT_PATH = "/account";

/** The Sysadmin's section: organizations, accounts, platform activity and
 * security defaults. */
export const PLATFORM_PATH = "/platform";
