variable "NAME" {
  default = "docker.io/vladpunko/pyftpkit"
}

variable "TAG" {
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
  tags = ["${NAME}:${TAG}"]
}

target "arm64" {
  args = {
    "BASE_IMAGE" = "vladpunko/python3-pyftpkit:3.12-qemuarm64"
  }
  context = "."
  platforms = ["linux/arm64"]
  tags = ["${NAME}:${TAG}-aarch64"]
}
