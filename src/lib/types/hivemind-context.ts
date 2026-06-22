export type HivemindContextMetadata = Record<string, unknown>;

export type HivemindContextSourceType =
	| 'chat'
	| 'file'
	| 'memory'
	| 'note'
	| 'url'
	| 'workspace'
	| (string & {});

export type HivemindContextSourceStatus =
	| 'available'
	| 'indexing'
	| 'stale'
	| 'error'
	| (string & {});

export type HivemindContextSource = {
	id: string;
	type: HivemindContextSourceType;
	name?: string | null;
	title?: string | null;
	uri?: string | null;
	path?: string | null;
	status?: HivemindContextSourceStatus | null;
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextPlanRequest = {
	query: string;
	chat_id?: string | null;
	message_id?: string | null;
	source_ids?: string[];
	metadata?: HivemindContextMetadata;
};

export type HivemindContextPlanStep = {
	id?: string;
	title: string;
	description?: string | null;
	source_ids?: string[];
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextPlanResponse = {
	plan_id?: string | null;
	steps: HivemindContextPlanStep[];
	sources?: HivemindContextSource[];
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextSearchRequest = {
	query: string;
	chat_id?: string | null;
	source_ids?: string[];
	limit?: number;
	offset?: number;
	filters?: HivemindContextMetadata;
	include_content?: boolean;
};

export type HivemindContextSearchResult = {
	id: string;
	source_id?: string | null;
	title?: string | null;
	snippet?: string | null;
	content?: string | null;
	score?: number | null;
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextSearchResponse = {
	results: HivemindContextSearchResult[];
	total?: number | null;
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextSourcesRequest = {
	query?: string | null;
	source_types?: HivemindContextSourceType[];
	include_status?: boolean;
	limit?: number;
	offset?: number;
};

export type HivemindContextSourcesResponse = {
	sources: HivemindContextSource[];
	total?: number | null;
	metadata?: HivemindContextMetadata | null;
};

export type HivemindContextReindexRequest = {
	source_ids?: string[];
	force?: boolean;
	metadata?: HivemindContextMetadata;
};

export type HivemindContextReindexStatus =
	| 'queued'
	| 'running'
	| 'completed'
	| 'failed'
	| (string & {});

export type HivemindContextReindexResponse = {
	job_id?: string | null;
	status?: HivemindContextReindexStatus;
	source_ids?: string[];
	metadata?: HivemindContextMetadata | null;
};
