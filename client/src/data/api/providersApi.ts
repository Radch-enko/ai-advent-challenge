import { Provider, ProviderModel } from '../../domain/models/provider'
import { request } from './request'

export function getModels(provider: Provider): Promise<ProviderModel[]> {
  return request(`/providers/${provider}/models`)
}
