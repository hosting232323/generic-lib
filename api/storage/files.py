FILE_TYPES = {
  'jpg': 'image/jpeg',
  'jpeg': 'image/jpeg',
  'png': 'image/png',
  'webp': 'image/webp',
  'pdf': 'application/pdf',
  'xls': 'application/vnd.ms-excel',
  'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'mp4': 'video/mp4',
}

IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
PDF_EXTENSIONS = ['pdf']
SPREADSHEET_EXTENSIONS = ['xls', 'xlsx']
VIDEO_EXTENSIONS = ['mp4']

DEFAULT_EXTENSIONS = IMAGE_EXTENSIONS + PDF_EXTENSIONS + SPREADSHEET_EXTENSIONS + VIDEO_EXTENSIONS


def get_extension(file) -> str:
  name = getattr(file, 'filename', '') or ''
  index = name.rfind('.')
  return '' if index < 0 else name[index + 1 :].lower()


def validate_files(files, extensions=DEFAULT_EXTENSIONS):
  invalid = []
  for file in files:
    extension = get_extension(file)
    if extension in extensions:
      continue
    # senza estensione nel nome si ricade sul mime dichiarato dal client
    if not extension and any(FILE_TYPES[allowed] == file.mimetype for allowed in extensions):
      continue
    invalid.append(f'.{extension}' if extension else (file.filename or file.mimetype))

  if not invalid:
    return None

  names = ', '.join(dict.fromkeys(invalid))
  allowed = ', '.join(f'.{extension}' for extension in extensions)
  return f'Estensione non supportata: {names}.\nEstensioni ammesse: {allowed}'
