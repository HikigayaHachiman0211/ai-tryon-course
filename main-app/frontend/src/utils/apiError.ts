import { isAxiosError } from 'axios';
import type { ErrorResponse } from '../types';

export const toApiError = (err: unknown, fallbackMessage = 'Request failed'): ErrorResponse['error'] => {
  if (isAxiosError<ErrorResponse>(err) && err.response?.data?.error) {
    const backendError = err.response.data.error;
    return {
      ...backendError,
      message: 'Request failed',
      request_id: backendError.request_id || 'unknown',
    };
  }
  if (err instanceof Error) {
    return {
      code: 'SYS-XXX',
      message: fallbackMessage,
      request_id: 'unknown',
      details: err.message,
    };
  }
  return {
    code: 'SYS-XXX',
    message: fallbackMessage,
    request_id: 'unknown',
    details: err,
  };
};
