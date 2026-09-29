import { getModels } from '../../../data/api/providersApi'
import { Provider, ProviderModel } from '../../../domain/models/provider'

export function loadProviderModels(
  provider: Provider,
  setModels: (models: ProviderModel[]) => void,
  setLoading: (loading: boolean) => void,
) {
  queueMicrotask(() => setLoading(true))
  void getModels(provider)
    .then(setModels)
    .catch(() => setModels([]))
    .finally(() => setLoading(false))
}
