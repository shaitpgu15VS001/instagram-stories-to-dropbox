from .rclone_uploader import RcloneUploader


class DropboxUploader(RcloneUploader):

    def __init__(self, app_key=None, app_secret=None, refresh_token=None, config_path="rclone.conf"):
        super().__init__(remote_name="dropbox", config_path=config_path)
