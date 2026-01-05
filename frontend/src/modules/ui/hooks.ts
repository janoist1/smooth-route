import { useSearchParams } from 'react-router-dom'

export interface UsePaginationProps {
  totalCount: number
  pageSize: number
  pageParamName?: string
}

export const usePagination = ({
  totalCount,
  pageSize,
  pageParamName = 'page',
}: UsePaginationProps) => {
  const [searchParams, setSearchParams] = useSearchParams()

  const pageParam = searchParams.get(pageParamName)
  const currentPage = pageParam ? Math.max(1, parseInt(pageParam, 10)) : 1

  const totalPages = Math.max(1, Math.ceil((totalCount || 0) / pageSize))
  const offset = (currentPage - 1) * pageSize

  const goToPage = (page: number) => {
    const newParams = new URLSearchParams(searchParams)
    newParams.set(pageParamName, String(page))
    setSearchParams(newParams)
    // Optional: scroll to top logic can be handled by consumer
  }

  return {
    currentPage,
    totalPages,
    offset,
    goToPage,
  }
}
