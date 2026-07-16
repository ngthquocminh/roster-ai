import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router/dom'
import './index.css'
import { router } from './App'

// Module-scope instance — created once so the cache survives re-renders.
// Nothing queries yet, but plans 01-06/01-07 add the first useQuery/
// useMutation calls, which is why the provider must already sit above the
// router: inverted nesting produces a runtime error at a distance that
// names the query, not the missing provider.
const queryClient = new QueryClient()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
