import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { SearchesPage } from './pages/SearchesPage'
import { RunPage } from './pages/RunPage'
import { ComparePage } from './pages/ComparePage'
import { LaunchPage } from './pages/LaunchPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { ForecastPage } from './pages/ForecastPage'
import { ResearchPage } from './pages/ResearchPage'
import { HealthPage } from './pages/HealthPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: false } },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<SearchesPage />} />
            <Route path="/runs/:runId" element={<RunPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route path="/launch" element={<LaunchPage />} />
            <Route path="/datasets" element={<DatasetsPage />} />
            <Route path="/forecast" element={<ForecastPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/health" element={<HealthPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
