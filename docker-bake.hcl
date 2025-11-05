variable "NAME" {
  default = "docker.io/vladpunko/pyftpkit"
}

variable "IMAGE_TAG" {
  default = "latest"
}

group "default" {
  targets = ["amd64", "arm64"]
}

target "amd64" {
  args = {
    "BASE_IMAGE" = "vladpunko/python3-pyftpkit:3.12-qemux86-64"
  }
  context = "."
  platforms = ["linux/amd64"]
  tags = ["${NAME}:${IMAGE_TAG}-amd64"]
}

target "arm64" {
  args = {
    "BASE_IMAGE" = "vladpunko/python3-pyftpkit:3.12-qemuarm64"
  }
  context = "."
  platforms = ["linux/arm64"]
  tags = ["${NAME}:${IMAGE_TAG}-arm64"]
}
