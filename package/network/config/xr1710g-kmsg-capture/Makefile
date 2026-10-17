# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
PKG_NAME:=xr1710g-kmsg-capture
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
include $(INCLUDE_DIR)/package.mk
define Package/xr1710g-kmsg-capture
 SECTION:=utils
 CATEGORY:=Utilities
 TITLE:=Bounded one-boot kernel first-fault retention for XR1710G
 DEPENDS:=+xr1710g-ap-defaults
endef
define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef
define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror $(PKG_BUILD_DIR)/capture.c $(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/xr-kmsg-capture
endef
define Package/xr1710g-kmsg-capture/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr-kmsg-capture $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr-kmsg-once $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr1710g_kmsg_capture $(1)/etc/init.d/
endef
$(eval $(call BuildPackage,xr1710g-kmsg-capture))
