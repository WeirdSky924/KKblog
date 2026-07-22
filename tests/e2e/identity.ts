import { existsSync, realpathSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { relative, resolve } from "node:path";

export const identityNames = ["visitor", "user", "author", "admin"] as const;
export type IdentityName = (typeof identityNames)[number];

const stateEnvironment: Record<Exclude<IdentityName, "visitor">, string> = {
  user: "KAJ_E2E_USER_STATE",
  author: "KAJ_E2E_AUTHOR_STATE",
  admin: "KAJ_E2E_ADMIN_STATE",
};

export function storageStateEnvironmentFor(
  identity: IdentityName,
): string | undefined {
  return identity === "visitor" ? undefined : stateEnvironment[identity];
}

export function storageStateFor(identity: IdentityName): string | undefined {
  const environmentName = storageStateEnvironmentFor(identity);
  if (!environmentName) {
    return undefined;
  }
  const configured = process.env[environmentName];
  if (!configured || !existsSync(configured)) {
    throw new Error(`${environmentName} is required for the ${identity} browser flow`);
  }
  const statePath = realpathSync(resolve(configured));
  const temporaryRoot = realpathSync(tmpdir());
  if (
    relative(temporaryRoot, statePath).startsWith("..") ||
    (statSync(statePath).mode & 0o777) !== 0o600
  ) {
    throw new Error(`${environmentName} must name a mode-0600 file under /tmp`);
  }
  return statePath;
}
