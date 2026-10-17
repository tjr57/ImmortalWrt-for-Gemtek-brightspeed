# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk
PKG_NAME:=xr1710g-diag-recovery
PKG_RELEASE:=6
PKG_LICENSE:=GPL-2.0-only
include $(INCLUDE_DIR)/package.mk

define Package/xr1710g-diag-recovery
 SECTION:=utils
 CATEGORY:=Utilities
 TITLE:=Opt-in diagnostic recovery with independent deadline for XR1710G
 DEPENDS:=+xr1710g-ap-defaults
endef

define Build/Prepare
	$(call Build/Prepare/Default)
	$(CP) ./src/* $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror $(PKG_BUILD_DIR)/capture.c $(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/xr-diag-capture
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror $(PKG_BUILD_DIR)/recovery.c $(TARGET_LDFLAGS) -o $(PKG_BUILD_DIR)/xr-diag-recovery
endef

define Package/xr1710g-diag-recovery/install
	$(INSTALL_DIR) $(1)/usr/libexec $(1)/etc/init.d
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr-diag-capture $(1)/usr/libexec/
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/xr-diag-recovery $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr-recovery-once $(1)/usr/libexec/
	$(INSTALL_BIN) ./files/xr_diag_recovery $(1)/etc/init.d/
endef
$(eval $(call BuildPackage,xr1710g-diag-recovery))
