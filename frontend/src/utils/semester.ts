// src/utils/semester.ts
export function formatSemesterDisplay(year: number, semester: number | string): string {
  if (year === 2) {
    if (semester === 3 || semester === '3') return 'Sem 3';
    if (semester === 4 || semester === '4') return 'Sem 4';
    if (semester === '3 & 4') return 'Sem 3&4';
  } else {
    if (semester === 1 || semester === '1') return 'Sem 1';
    if (semester === 2 || semester === '2') return 'Sem 2';
    if (semester === '1 & 2') return 'Sem 1&2';
  }
  return String(semester);
}

export function getSemesterOptions(year: number) {
  if (year === 2) {
    return [
      { value: '3', label: 'Semester 3' },
      { value: '4', label: 'Semester 4' },
      { value: '3 & 4', label: 'Both (3 & 4)' },
    ];
  }
  return [
    { value: '1', label: 'Semester 1' },
    { value: '2', label: 'Semester 2' },
    { value: '1 & 2', label: 'Both (1 & 2)' },
  ];
}

export function formatPrice(price: number | null, isNegotiable: boolean): string {
  if (price == null) return 'ညှိနှိုင်း';
  const formatted = price.toLocaleString('en-US');
  return isNegotiable ? `${formatted} MMK (ညှိနှိုင်း)` : `${formatted} MMK`;
}

export function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    Available: 'ရနိုင်သည်',
    Pending: 'လုပ်ဆောင်နေသည်',
    Sold: 'ရောင်းပြီး',
    Cancelled: 'ပယ်ဖျက်ပြီး',
    Delisted: 'ဖျက်ထားသည်',
    Deleted: 'ဖျက်ပြီး',
  };
  return labels[status] || status;
}

export function getStatusBadgeClass(status: string): string {
  const classes: Record<string, string> = {
    Available: 'badge badge-available',
    Pending: 'badge badge-pending',
    Sold: 'badge badge-sold',
    Cancelled: 'badge badge-cancelled',
    Delisted: 'badge badge-delisted',
    Deleted: 'badge badge-cancelled',
  };
  return classes[status] || 'badge badge-cancelled';
}
