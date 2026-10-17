# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
PKG_NAME:=xr1710g-npu-diagnostic
PKG_RELEASE:=4
PKG_LICENSE:=GPL-2.0-only
include $(INCLUDE_DIR)/package.mk
define Package/xr1710g-npu-diagnostic
 SECTION:=utils
 CATEGORY:=Utilities
 TITLE:=Guarded one-boot NPU diagnostic activation for XR1710G
 DEPENDS:=+xr1710g-diag-recovery +libjson-c
endef
define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef
define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror $(PKG_BUILD_DIR)/activate.c $(TARGET_LDFLAGS) -ljson-c -o $(PKG_BUILD_DIR)/xr-diag-activate
endef
define Package/xr1710g-npu-diagnostic/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr-diag-activate $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr-npu-guarded-once $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr_guarded_npu $(1)/etc/init.d/
endef
$(eval $(call BuildPackage,xr1710g-npu-diagnostic))
