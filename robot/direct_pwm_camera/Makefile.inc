USE_RASPIKE_ART=1

mkfile_path := $(dir $(lastword $(MAKEFILE_LIST)))

APPL_COBJS +=\
DirectPwmController.o\
PwmClient.o\

APPL_DIRS += $(mkfile_path)DirectPwmController

INCLUDES += \
	-I$(mkfile_path)DirectPwmController
