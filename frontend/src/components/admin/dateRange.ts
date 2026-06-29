export function dayStartTs(date: string) {
  return new Date(date + 'T00:00:00').getTime() / 1000
}

export function nextDayStartTs(date: string) {
  const d = new Date(date + 'T00:00:00')
  d.setDate(d.getDate() + 1)
  return d.getTime() / 1000
}
