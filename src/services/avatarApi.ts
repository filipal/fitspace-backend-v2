const ensureTrailingSlash = (value: string): string =>
  value.endsWith('/') ? value : `${value}/`;

const trimTrailingSlashes = (value: string): string => value.replace(/\/+$/u, '');

const encodePathSegment = (segment: string): string => encodeURIComponent(segment);

const resolveUserRootUrl = (baseUrl: string, userId: string): string => {
  const normalisedBase = ensureTrailingSlash(trimTrailingSlashes(baseUrl));
  return `${normalisedBase}${encodePathSegment(userId)}`;
};

const buildAvatarScopedUrl = (
  baseUrl: string,
  userId: string,
  ...segments: string[]
): string => {
  const avatarRoot = `${ensureTrailingSlash(resolveUserRootUrl(baseUrl, userId))}avatars`;
  if (!segments.length) {
    return avatarRoot;
  }

  const suffix = segments.map(encodePathSegment).join('/');
  return `${avatarRoot}/${suffix}`;
};

export const resolveAvatarCollectionUrl = (baseUrl: string, userId: string): string =>
  buildAvatarScopedUrl(baseUrl, userId);

export const resolveAvatarUrl = (
  baseUrl: string,
  userId: string,
  avatarId: string
): string => buildAvatarScopedUrl(baseUrl, userId, avatarId);

export const resolveAvatarMeasurementsUrl = (
  baseUrl: string,
  userId: string,
  avatarId: string
): string => buildAvatarScopedUrl(baseUrl, userId, avatarId, 'measurements');

export const resolveAvatarMorphTargetsUrl = (
  baseUrl: string,
  userId: string,
  avatarId: string
): string => buildAvatarScopedUrl(baseUrl, userId, avatarId, 'morph-targets');

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface AvatarRequestConfig {
  url: string;
  init: RequestInit;
}

const createJsonRequestInit = (
  method: string,
  body: JsonValue | JsonValue[] | undefined,
  init?: RequestInit
): RequestInit => {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return {
    ...init,
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  };
};

export const createAvatarRequest = (
  baseUrl: string,
  userId: string,
  payload: JsonValue | JsonValue[],
  init?: RequestInit
): AvatarRequestConfig => ({
  url: resolveAvatarCollectionUrl(baseUrl, userId),
  init: createJsonRequestInit('POST', payload, init),
});

export const updateAvatarMeasurementsRequest = (
  baseUrl: string,
  userId: string,
  avatarId: string,
  payload: JsonValue | JsonValue[],
  init?: RequestInit
): AvatarRequestConfig => ({
  url: resolveAvatarMeasurementsUrl(baseUrl, userId, avatarId),
  init: createJsonRequestInit('PATCH', payload, init),
});

export const updateAvatarMorphTargetsRequest = (
  baseUrl: string,
  userId: string,
  avatarId: string,
  payload: JsonValue | JsonValue[],
  init?: RequestInit
): AvatarRequestConfig => ({
  url: resolveAvatarMorphTargetsUrl(baseUrl, userId, avatarId),
  init: createJsonRequestInit('PATCH', payload, init),
});

export const fetchAvatarByIdRequest = (
  baseUrl: string,
  userId: string,
  avatarId: string,
  init?: RequestInit
): AvatarRequestConfig => ({
  url: resolveAvatarUrl(baseUrl, userId, avatarId),
  init: {
    ...init,
    method: init?.method ?? 'GET',
  },
});