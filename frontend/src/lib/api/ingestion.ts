import { api } from './client';
import { StreamStatus, FlaggedRecord } from '@/types/ingestion';
import { MOCK_STREAMS, MOCK_RECORDS } from '@/lib/fixtures';

export async function getIngestionStatus(): Promise<StreamStatus[]> {
  try {
    return await api<StreamStatus[]>('/ingestion/status');
  } catch {
    return MOCK_STREAMS;
  }
}

export async function getFlaggedRecords(): Promise<FlaggedRecord[]> {
  try {
    return await api<FlaggedRecord[]>('/ingestion/flagged');
  } catch {
    return MOCK_RECORDS;
  }
}
