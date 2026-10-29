export function formatTimestamp(value: string, locale: string): string {
  const options: Intl.DateTimeFormatOptions = {timeZone:'Europe/Sofia',year:'numeric',month:'short',day:'numeric',
    hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}
  const timestamp = new Date(value)
  if (!Number.isFinite(timestamp.getTime())) return '—'
  let formatter: Intl.DateTimeFormat
  try { formatter = new Intl.DateTimeFormat(locale,options) }
  catch { formatter = new Intl.DateTimeFormat('en',options) }
  const formatted = formatter.format(timestamp)
  // Sofia's autumn clock change repeats an hour. Only those ambiguous times
  // need an offset to distinguish two different instants.
  const hour = 60 * 60 * 1000
  const repeated = [-hour, hour].some(delta => formatter.format(new Date(timestamp.getTime() + delta)) === formatted)
  if (!repeated) return formatted
  const offset = new Intl.DateTimeFormat('en', {timeZone:'Europe/Sofia',timeZoneName:'shortOffset'})
    .formatToParts(timestamp).find(part => part.type === 'timeZoneName')?.value
  const match = offset?.match(/^GMT([+-])(\d{1,2})(?::(\d{2}))?$/)
  return match ? `${formatted} (${match[1]}${match[2].padStart(2,'0')}:${match[3] || '00'})` : formatted
}
