import { isAxiosError } from 'axios';
import type { ErrorResponse } from '../types';

export const toApiError = (err: unknown, fallbackMessage = '网络请求失败，请检查后端服务是否已启动'): ErrorResponse['error'] => {
  if (isAxiosError<ErrorResponse>(err) && err.response?.data?.error) {
    return err.response.data.error;
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
