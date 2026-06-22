import { WEBUI_API_BASE_URL } from '$lib/constants';
import type {
	HivemindContextPlanRequest,
	HivemindContextPlanResponse,
	HivemindContextReindexRequest,
	HivemindContextReindexResponse,
	HivemindContextSearchRequest,
	HivemindContextSearchResponse,
	HivemindContextSourcesRequest,
	HivemindContextSourcesResponse
} from '$lib/types/hivemind-context';

const HIVEMIND_CONTEXT_API_BASE_URL = `${WEBUI_API_BASE_URL}/context`;

const getHeaders = (token: string) => ({
	Accept: 'application/json',
	'Content-Type': 'application/json',
	...(token && { authorization: `Bearer ${token}` })
});

const getErrorDetail = (err: unknown) => {
	if (err && typeof err === 'object' && 'detail' in err) {
		return err.detail;
	}

	return err;
};

const postHivemindContext = async <TResponse, TRequest extends object>(
	token: string,
	path: string,
	payload: TRequest
): Promise<TResponse> => {
	let error: unknown = null;

	const res = await fetch(`${HIVEMIND_CONTEXT_API_BASE_URL}/${path}`, {
		method: 'POST',
		headers: getHeaders(token),
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json() as Promise<TResponse>;
		})
		.catch((err) => {
			error = getErrorDetail(err);
			console.error(err);
			return null;
		});

	if (error !== null) {
		throw error;
	}

	return res as TResponse;
};

export const getHivemindContextPlan = async (
	token: string,
	payload: HivemindContextPlanRequest
): Promise<HivemindContextPlanResponse> => postHivemindContext(token, 'plan', payload);

export const searchHivemindContext = async (
	token: string,
	payload: HivemindContextSearchRequest
): Promise<HivemindContextSearchResponse> => postHivemindContext(token, 'search', payload);

export const getHivemindContextSources = async (
	token: string,
	payload: HivemindContextSourcesRequest = {}
): Promise<HivemindContextSourcesResponse> => postHivemindContext(token, 'sources', payload);

export const reindexHivemindContext = async (
	token: string,
	payload: HivemindContextReindexRequest = {}
): Promise<HivemindContextReindexResponse> => postHivemindContext(token, 'reindex', payload);
